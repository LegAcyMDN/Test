# app.py - API Flask pour la modération
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta
import hashlib
import json
from functools import wraps
from collections import defaultdict
import time

from config import Config
from model_training import ToxicityModel
from data_preprocessing import DataPreprocessor

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Initialisation Supabase
supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)

# Initialisation du modèle IA
model = ToxicityModel()
model.load_model(Config.MODEL_PATH)

# Préprocesseur
preprocessor = DataPreprocessor()

# Rate limiting simple (en mémoire)
request_history = defaultdict(list)


# === UTILITAIRES ===

def anonymize_user_id(user_id):
    """Anonymise l'ID utilisateur pour RGPD"""
    if Config.ANONYMIZE_LOGS:
        return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
    return str(user_id)


def rate_limit(max_requests=Config.MAX_REQUESTS_PER_MINUTE):
    """Décorateur de rate limiting"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            now = time.time()
            minute_ago = now - 60
            
            # Identifier le client
            client_id = request.headers.get('X-Client-ID') or request.remote_addr
            
            # Nettoyer l'historique
            request_history[client_id] = [
                ts for ts in request_history[client_id] if ts > minute_ago
            ]
            
            # Vérifier la limite
            if len(request_history[client_id]) >= max_requests:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': 60
                }), 429
            
            # Ajouter la requête
            request_history[client_id].append(now)
            
            return f(*args, **kwargs)
        return wrapped
    return decorator


def log_detection(data):
    """Enregistre une détection dans Supabase"""
    try:
        # Préparer les données
        log_entry = {
            'user_id': anonymize_user_id(data.get('user_id')),
            'guild_id': data.get('guild_id'),
            'channel_id': data.get('channel_id'),
            'message_id': data.get('message_id'),
            'message_content': data.get('message_content') if not Config.ANONYMIZE_LOGS else '[REDACTED]',
            'message_hash': hashlib.sha256(data.get('message_content', '').encode()).hexdigest(),
            'is_toxic': data.get('is_toxic'),
            'confidence': data.get('confidence'),
            'toxic_probability': data.get('toxic_probability'),
            'language': data.get('language'),
            'action_taken': data.get('action_taken'),
            'moderator_validated': data.get('moderator_validated'),
            'severity_score': data.get('severity_score'),
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Insérer dans Supabase
        result = supabase.table('moderation_logs').insert(log_entry).execute()
        
        return result.data[0] if result.data else None
        
    except Exception as e:
        print(f"Erreur lors du logging : {e}")
        return None


def get_guild_config(guild_id):
    """Récupère la configuration d'un serveur"""
    try:
        result = supabase.table('guild_configs').select('*').eq('guild_id', guild_id).execute()
        
        if result.data:
            return result.data[0]
        
        # Configuration par défaut
        return {
            'guild_id': guild_id,
            'tolerance_level': Config.CONFIDENCE_HIGH,
            'active_languages': ['en', 'fr'],
            'auto_sanctions': True,
            'whitelist_words': [],
            'auto_warn_threshold': 0.9,
            'auto_mute_threshold': 0.95,
            'auto_ban_threshold': 0.98
        }
    
    except Exception as e:
        print(f"Erreur configuration serveur : {e}")
        return None


def check_context_exceptions(text):
    """Vérifie si le message contient des citations ou contextes particuliers"""
    # Patterns de citations
    citation_patterns = [
        r'il m\'a (dit|traité|appelé)',
        r'on m\'a (dit|traité|appelé)',
        r'quelqu\'un m\'a (dit|traité|appelé)',
        r'(quote|citation|cité)\s*:',
        r'\"[^\"]+\"',  # Texte entre guillemets
    ]
    
    import re
    for pattern in citation_patterns:
        if re.search(pattern, text.lower()):
            return True
    
    return False


def calculate_sanction_level(user_id, guild_id):
    """Calcule le niveau de sanction basé sur l'historique"""
    try:
        # Récupérer l'historique des 30 derniers jours
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        result = supabase.table('moderation_logs').select('*').eq(
            'user_id', anonymize_user_id(user_id)
        ).eq(
            'guild_id', guild_id
        ).eq(
            'is_toxic', True
        ).gte(
            'created_at', thirty_days_ago
        ).execute()
        
        infractions = len(result.data) if result.data else 0
        
        # Déterminer le niveau
        if infractions == 0:
            return 'warn'
        elif infractions == 1:
            return 'mute'
        else:
            return 'ban'
    
    except Exception as e:
        print(f"Erreur calcul niveau sanction : {e}")
        return 'warn'


# === ENDPOINTS ===

@app.route('/health', methods=['GET'])
def health_check():
    """Vérification de l'état du service"""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model.model is not None,
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/analyze', methods=['POST'])
@rate_limit()
def analyze_message():
    """Analyse un message pour détecter la toxicité"""
    try:
        data = request.json
        
        # Validation des données
        if not data or 'message' not in data:
            return jsonify({'error': 'Message manquant'}), 400
        
        message = data['message']
        user_id = data.get('user_id')
        guild_id = data.get('guild_id')
        channel_id = data.get('channel_id')
        message_id = data.get('message_id')
        
        # Vérifier la longueur minimale
        if len(message.strip()) < Config.MIN_MESSAGE_LENGTH:
            return jsonify({
                'should_moderate': False,
                'reason': 'Message trop court'
            })
        
        # Nettoyer le message
        clean_message = preprocessor.clean_text(message)
        
        if len(clean_message.strip()) < Config.MIN_MESSAGE_LENGTH:
            return jsonify({
                'should_moderate': False,
                'reason': 'Message vide après nettoyage'
            })
        
        # Détecter la langue
        language = preprocessor.detect_language(clean_message)
        
        # Récupérer la configuration du serveur
        guild_config = get_guild_config(guild_id)
        
        # Vérifier si la langue est active
        if language not in guild_config.get('active_languages', ['en', 'fr']):
            return jsonify({
                'should_moderate': False,
                'reason': f'Langue {language} non surveillée'
            })
        
        # Vérifier les exceptions de contexte
        if check_context_exceptions(clean_message):
            return jsonify({
                'should_moderate': False,
                'reason': 'Citation ou contexte détecté',
                'language': language
            })
        
        # Prédiction IA
        prediction = model.predict(clean_message)
        
        # Déterminer l'action
        confidence = prediction['confidence']
        is_toxic = prediction['is_toxic']
        toxic_prob = prediction['toxic_probability']
        
        action = 'none'
        requires_validation = False
        
        if is_toxic:
            if confidence >= Config.CONFIDENCE_HIGH:
                # Auto-sanction
                sanction_level = calculate_sanction_level(user_id, guild_id)
                action = sanction_level
                requires_validation = False
            elif confidence >= Config.CONFIDENCE_LOW:
                # Demande validation
                action = 'pending_review'
                requires_validation = True
        
        # Préparer la réponse
        response = {
            'should_moderate': is_toxic and confidence >= Config.CONFIDENCE_LOW,
            'is_toxic': is_toxic,
            'confidence': confidence,
            'toxic_probability': toxic_prob,
            'language': language,
            'action': action,
            'requires_validation': requires_validation,
            'severity_score': toxic_prob,
            'analysis_timestamp': datetime.utcnow().isoformat()
        }
        
        # Logger la détection
        log_data = {
            'user_id': user_id,
            'guild_id': guild_id,
            'channel_id': channel_id,
            'message_id': message_id,
            'message_content': message,
            'is_toxic': is_toxic,
            'confidence': confidence,
            'toxic_probability': toxic_prob,
            'language': language,
            'action_taken': action,
            'moderator_validated': None,
            'severity_score': toxic_prob
        }
        
        log_id = log_detection(log_data)
        if log_id:
            response['log_id'] = log_id.get('id') if isinstance(log_id, dict) else log_id
        
        return jsonify(response)
    
    except Exception as e:
        print(f"Erreur analyse : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/validate', methods=['POST'])
def validate_detection():
    """Valide ou rejette une détection par un modérateur"""
    try:
        data = request.json
        
        log_id = data.get('log_id')
        is_valid = data.get('is_valid')
        moderator_id = data.get('moderator_id')
        action_taken = data.get('action_taken')
        
        if not log_id or is_valid is None:
            return jsonify({'error': 'Données manquantes'}), 400
        
        # Mettre à jour le log
        update_data = {
            'moderator_validated': is_valid,
            'moderator_id': anonymize_user_id(moderator_id),
            'action_taken': action_taken if is_valid else 'dismissed',
            'validated_at': datetime.utcnow().isoformat()
        }
        
        result = supabase.table('moderation_logs').update(update_data).eq('id', log_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Validation enregistrée',
            'data': result.data[0] if result.data else None
        })
    
    except Exception as e:
        print(f"Erreur validation : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/history/<user_id>', methods=['GET'])
def get_user_history(user_id):
    """Récupère l'historique de modération d'un utilisateur"""
    try:
        guild_id = request.args.get('guild_id')
        limit = int(request.args.get('limit', 50))
        
        query = supabase.table('moderation_logs').select('*').eq(
            'user_id', anonymize_user_id(user_id)
        )
        
        if guild_id:
            query = query.eq('guild_id', guild_id)
        
        result = query.order('created_at', desc=True).limit(limit).execute()
        
        return jsonify({
            'user_id': anonymize_user_id(user_id),
            'total_infractions': len(result.data) if result.data else 0,
            'history': result.data
        })
    
    except Exception as e:
        print(f"Erreur historique : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/config/<guild_id>', methods=['GET', 'POST'])
def guild_configuration(guild_id):
    """Gère la configuration d'un serveur"""
    try:
        if request.method == 'GET':
            config = get_guild_config(guild_id)
            return jsonify(config)
        
        elif request.method == 'POST':
            data = request.json
            
            # Valider les données
            allowed_fields = [
                'tolerance_level', 'active_languages', 'auto_sanctions',
                'whitelist_words', 'auto_warn_threshold', 'auto_mute_threshold',
                'auto_ban_threshold'
            ]
            
            update_data = {k: v for k, v in data.items() if k in allowed_fields}
            update_data['guild_id'] = guild_id
            update_data['updated_at'] = datetime.utcnow().isoformat()
            
            # Upsert configuration
            result = supabase.table('guild_configs').upsert(update_data).execute()
            
            return jsonify({
                'success': True,
                'config': result.data[0] if result.data else None
            })
    
    except Exception as e:
        print(f"Erreur configuration : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/stats/<guild_id>', methods=['GET'])
def guild_statistics(guild_id):
    """Statistiques de modération pour un serveur"""
    try:
        # Période
        days = int(request.args.get('days', 30))
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Récupérer les logs
        result = supabase.table('moderation_logs').select('*').eq(
            'guild_id', guild_id
        ).gte(
            'created_at', start_date
        ).execute()
        
        logs = result.data if result.data else []
        
        # Calculer les statistiques
        total_messages = len(logs)
        toxic_messages = sum(1 for log in logs if log.get('is_toxic'))
        auto_moderated = sum(1 for log in logs if log.get('action_taken') not in ['none', 'pending_review', 'dismissed'])
        pending_review = sum(1 for log in logs if log.get('action_taken') == 'pending_review')
        
        # Par langue
        languages = {}
        for log in logs:
            lang = log.get('language', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
        
        # Par action
        actions = {}
        for log in logs:
            action = log.get('action_taken', 'none')
            actions[action] = actions.get(action, 0) + 1
        
        return jsonify({
            'guild_id': guild_id,
            'period_days': days,
            'total_messages_analyzed': total_messages,
            'toxic_detected': toxic_messages,
            'auto_moderated': auto_moderated,
            'pending_review': pending_review,
            'toxicity_rate': round(toxic_messages / total_messages * 100, 2) if total_messages > 0 else 0,
            'languages': languages,
            'actions': actions
        })
    
    except Exception as e:
        print(f"Erreur statistiques : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/retrain', methods=['POST'])
def retrain_model():
    """Déclenche un réentraînement du modèle (apprentissage continu)"""
    try:
        # Récupérer les logs validés récents
        result = supabase.table('moderation_logs').select('*').not_.is_(
            'moderator_validated', 'null'
        ).limit(10000).execute()
        
        if not result.data or len(result.data) < 100:
            return jsonify({
                'success': False,
                'message': 'Pas assez de données validées pour réentraîner'
            })
        
        # TODO: Implémenter la logique de réentraînement
        # 1. Préparer les nouvelles données
        # 2. Fine-tuner le modèle existant
        # 3. Sauvegarder le nouveau modèle
        
        return jsonify({
            'success': True,
            'message': 'Réentraînement programmé',
            'data_count': len(result.data)
        })
    
    except Exception as e:
        print(f"Erreur réentraînement : {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/cleanup', methods=['POST'])
def cleanup_old_logs():
    """Nettoie les anciens logs (conformité RGPD)"""
    try:
        # Date limite
        retention_date = (datetime.utcnow() - timedelta(days=Config.LOG_RETENTION_DAYS)).isoformat()
        
        # Supprimer les anciens logs
        result = supabase.table('moderation_logs').delete().lt(
            'created_at', retention_date
        ).execute()
        
        deleted_count = len(result.data) if result.data else 0
        
        return jsonify({
            'success': True,
            'deleted_logs': deleted_count,
            'retention_days': Config.LOG_RETENTION_DAYS
        })
    
    except Exception as e:
        print(f"Erreur nettoyage : {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=Config.DEBUG
    )