from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
from supabase import create_client, Client

# Imports pour l'IA
from ai_moderation.model_manager import ModelManager
from ai_moderation.text_processor import TextProcessor
from database.db_manager import DatabaseManager
from utils.logger import setup_logger

app = Flask(__name__)
CORS(app)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['JSON_AS_ASCII'] = False

# Configuration Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

# Initialisation des composants
logger = setup_logger('moderation_api')
db_manager = DatabaseManager(supabase_url)
text_processor = TextProcessor()
model_manager = ModelManager()

# Seuils de confiance configurables
CONFIDENCE_THRESHOLDS = {
    'auto_action': float(os.getenv('AUTO_ACTION_THRESHOLD', 0.9)),
    'moderator_review': float(os.getenv('MODERATOR_REVIEW_THRESHOLD', 0.5)),
    'ignore': float(os.getenv('IGNORE_THRESHOLD', 0.5))
}

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint pour vérifier l'état de l'API"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'model_loaded': model_manager.is_loaded()
    }), 200

@app.route('/api/v1/analyze', methods=['POST'])
def analyze_message():
    """
    Analyse un message pour détecter la toxicité
    
    Payload attendu:
    {
        "message": "texte à analyser",
        "user_id": "discord_user_id",
        "guild_id": "discord_guild_id",
        "channel_id": "discord_channel_id",
        "message_id": "discord_message_id",
        "username": "nom d'utilisateur (optionnel)"
    }
    """
    try:
        data = request.get_json()
        
        # Validation des données
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
        
        message = data.get('message', '').strip()
        user_id = data.get('user_id')
        guild_id = data.get('guild_id')
        channel_id = data.get('channel_id')
        message_id = data.get('message_id')
        username = data.get('username', 'Unknown')
        
        # Protection contre le spam
        if len(message) < 3:
            return jsonify({
                'analyzed': False,
                'reason': 'Message too short',
                'action': 'none'
            }), 200
        
        # Récupération de la configuration du serveur
        guild_config = db_manager.get_guild_config(guild_id)
        if not guild_config:
            guild_config = db_manager.create_default_guild_config(guild_id)
        
        # Vérifier si l'utilisateur a un rôle protégé
        user_roles = data.get('user_roles', [])
        if any(role in guild_config.get('protected_roles', []) for role in user_roles):
            logger.info(f"User {user_id} has protected role, skipping analysis")
            return jsonify({
                'analyzed': False,
                'reason': 'Protected role',
                'action': 'none'
            }), 200
        
        # Prétraitement du texte
        processed_text, detected_language = text_processor.process(message)
        
        # Vérification si la langue est supportée par la config du serveur
        if detected_language not in guild_config.get('active_languages', ['en', 'fr']):
            logger.info(f"Language {detected_language} not active for guild {guild_id}")
            return jsonify({
                'analyzed': False,
                'reason': 'Language not active',
                'action': 'none',
                'detected_language': detected_language
            }), 200
        
        # Vérification de la liste blanche
        if text_processor.is_whitelisted(processed_text, guild_config.get('whitelist', [])):
            logger.info(f"Message contains whitelisted content for guild {guild_id}")
            return jsonify({
                'analyzed': True,
                'is_toxic': False,
                'reason': 'Whitelisted content',
                'action': 'none'
            }), 200
        
        # Analyse par l'IA
        prediction = model_manager.predict(processed_text, detected_language)
        
        toxicity_score = prediction['toxicity_score']
        categories = prediction['categories']
        confidence = prediction['confidence']
        
        # Appliquer le niveau de tolérance du serveur
        tolerance = guild_config.get('tolerance_level', 1.0)
        adjusted_score = toxicity_score * tolerance
        
        # Déterminer l'action à prendre
        action = 'none'
        requires_review = False
        auto_sanction = False
        
        if adjusted_score >= CONFIDENCE_THRESHOLDS['auto_action']:
            action = determine_sanction_level(user_id, guild_id, categories, db_manager)
            auto_sanction = True
        elif adjusted_score >= CONFIDENCE_THRESHOLDS['moderator_review']:
            action = 'review_required'
            requires_review = True
        
        # Journalisation dans la base de données
        log_id = db_manager.log_detection(
            user_id=user_id,
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=message_id,
            message_content=message,
            toxicity_score=toxicity_score,
            adjusted_score=adjusted_score,
            categories=categories,
            language=detected_language,
            action_taken=action,
            requires_moderator_review=requires_review,
            confidence=confidence,
            username=username
        )
        
        # Incrémenter les infractions de l'utilisateur si toxique
        if adjusted_score >= CONFIDENCE_THRESHOLDS['moderator_review']:
            db_manager.increment_user_infractions(user_id, guild_id, categories)
        
        response = {
            'analyzed': True,
            'is_toxic': adjusted_score >= CONFIDENCE_THRESHOLDS['moderator_review'],
            'toxicity_score': float(toxicity_score),
            'adjusted_score': float(adjusted_score),
            'confidence': float(confidence),
            'categories': categories,
            'language': detected_language,
            'action': action,
            'requires_review': requires_review,
            'auto_sanction': auto_sanction,
            'log_id': log_id,
            'guild_config': {
                'tolerance_level': tolerance,
                'auto_sanctions_enabled': guild_config.get('auto_sanctions_enabled', False)
            }
        }
        
        logger.info(f"Analysis complete for message {message_id}: score={adjusted_score:.2f}, action={action}")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error analyzing message: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

@app.route('/api/v1/moderator/validate', methods=['POST'])
def moderator_validate():
    """
    Valide ou rejette une décision de l'IA
    
    Payload:
    {
        "log_id": "id du log",
        "moderator_id": "id du modérateur",
        "decision": "approve" ou "reject",
        "notes": "notes optionnelles"
    }
    """
    try:
        data = request.get_json()
        
        log_id = data.get('log_id')
        moderator_id = data.get('moderator_id')
        decision = data.get('decision')
        notes = data.get('notes', '')
        
        if not all([log_id, moderator_id, decision]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        if decision not in ['approve', 'reject']:
            return jsonify({'error': 'Invalid decision'}), 400
        
        # Mettre à jour le log avec la décision du modérateur
        success = db_manager.update_moderator_validation(
            log_id=log_id,
            moderator_id=moderator_id,
            approved=(decision == 'approve'),
            notes=notes
        )
        
        if success:
            # Si approuvé, ajouter aux données d'entraînement pour le retrain
            if decision == 'approve':
                db_manager.add_to_training_queue(log_id)
            
            logger.info(f"Moderator {moderator_id} {decision}d log {log_id}")
            return jsonify({'success': True, 'message': 'Validation recorded'}), 200
        else:
            return jsonify({'error': 'Log not found'}), 404
            
    except Exception as e:
        logger.error(f"Error in moderator validation: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/v1/config/guild/<guild_id>', methods=['GET', 'PUT'])
def guild_config(guild_id):
    """Récupère ou met à jour la configuration d'un serveur"""
    try:
        if request.method == 'GET':
            config = db_manager.get_guild_config(guild_id)
            if config:
                return jsonify(config), 200
            else:
                return jsonify({'error': 'Guild not found'}), 404
        
        elif request.method == 'PUT':
            data = request.get_json()
            success = db_manager.update_guild_config(guild_id, data)
            
            if success:
                return jsonify({'success': True, 'message': 'Configuration updated'}), 200
            else:
                return jsonify({'error': 'Failed to update configuration'}), 500
                
    except Exception as e:
        logger.error(f"Error managing guild config: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/v1/stats/guild/<guild_id>', methods=['GET'])
def guild_stats(guild_id):
    """Récupère les statistiques de modération d'un serveur"""
    try:
        days = request.args.get('days', 30, type=int)
        stats = db_manager.get_guild_stats(guild_id, days)
        return jsonify(stats), 200
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/v1/user/<user_id>/history/<guild_id>', methods=['GET'])
def user_history(user_id, guild_id):
    """Récupère l'historique des infractions d'un utilisateur"""
    try:
        limit = request.args.get('limit', 50, type=int)
        history = db_manager.get_user_history(user_id, guild_id, limit)
        return jsonify(history), 200
    except Exception as e:
        logger.error(f"Error fetching user history: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/v1/retrain', methods=['POST'])
def retrain_model():
    """Lance le réentraînement du modèle avec les nouvelles données validées"""
    try:
        # Vérification d'un token d'authentification
        auth_token = request.headers.get('Authorization')
        if auth_token != f"Bearer {os.getenv('ADMIN_TOKEN')}":
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Lancer le réentraînement de manière asynchrone
        training_data = db_manager.get_training_queue()
        
        if len(training_data) < 100:
            return jsonify({
                'message': 'Not enough training data',
                'current_samples': len(training_data),
                'required_samples': 100
            }), 400
        
        # Ici, vous devriez lancer le réentraînement de manière asynchrone
        # Pour l'instant, on simule
        logger.info(f"Starting model retraining with {len(training_data)} samples")
        
        return jsonify({
            'success': True,
            'message': 'Retraining started',
            'samples': len(training_data)
        }), 202
        
    except Exception as e:
        logger.error(f"Error starting retrain: {str(e)}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

def determine_sanction_level(user_id, guild_id, categories, db_manager):
    """
    Détermine le niveau de sanction en fonction de l'historique de l'utilisateur
    et de la gravité de l'infraction
    """
    infractions = db_manager.get_user_infractions_count(user_id, guild_id)
    
    # Calcul de la gravité basée sur les catégories
    severity_weights = {
        'toxic': 1,
        'severe_toxic': 3,
        'obscene': 2,
        'threat': 3,
        'insult': 1,
        'identity_hate': 3
    }
    
    severity = sum(severity_weights.get(cat, 1) for cat in categories)
    
    # Détermination de la sanction
    if infractions == 0:
        return 'warn'
    elif infractions == 1:
        if severity >= 3:
            return 'mute_1h'
        else:
            return 'warn'
    elif infractions == 2:
        if severity >= 3:
            return 'mute_24h'
        else:
            return 'mute_6h'
    else:
        if severity >= 3:
            return 'ban'
        else:
            return 'mute_48h'

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

    