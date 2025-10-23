import torch
import torch.nn as nn
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    CamembertForSequenceClassification,
    DistilBertForSequenceClassification
)
import numpy as np
import logging
import os
from pathlib import Path
import json

logger = logging.getLogger('moderation_api')

class ModelManager:
    """Gestionnaire des modèles d'IA pour la modération multilingue"""
    
    def __init__(self):
        self.models = {}
        self.tokenizers = {}
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_dir = Path('models')
        self.model_dir.mkdir(exist_ok=True)
        
        # Configuration des modèles par langue
        self.model_configs = {
            'fr': {
                'name': 'camembert-base',
                'path': 'camembert/camembert-base'
            },
            'en': {
                'name': 'distilbert-base-uncased',
                'path': 'distilbert-base-uncased'
            },
            'multilingual': {
                'name': 'xlm-roberta-base',
                'path': 'xlm-roberta-base'
            }
        }
        
        # Labels de classification
        self.labels = ['toxic', 'severe_toxic', 'obscene', 'threat', 'insult', 'identity_hate']
        self.num_labels = len(self.labels)
        
        # Charger les modèles
        self._load_models()
        
    def _load_models(self):
        """Charge les modèles pré-entraînés ou entraînés"""
        try:
            # Charger le modèle principal (multilingue par défaut)
            model_name = os.getenv('PRIMARY_MODEL', 'multilingual')
            
            if model_name in self.model_configs:
                config = self.model_configs[model_name]
                
                # Vérifier si un modèle fine-tuné existe
                custom_model_path = self.model_dir / f"{config['name']}_finetuned"
                
                if custom_model_path.exists():
                    logger.info(f"Loading fine-tuned model from {custom_model_path}")
                    self.models[model_name] = AutoModelForSequenceClassification.from_pretrained(
                        str(custom_model_path),
                        num_labels=self.num_labels
                    )
                    self.tokenizers[model_name] = AutoTokenizer.from_pretrained(str(custom_model_path))
                else:
                    logger.info(f"Loading pre-trained model: {config['path']}")
                    self.tokenizers[model_name] = AutoTokenizer.from_pretrained(config['path'])
                    self.models[model_name] = AutoModelForSequenceClassification.from_pretrained(
                        config['path'],
                        num_labels=self.num_labels,
                        problem_type="multi_label_classification"
                    )
                
                self.models[model_name].to(self.device)
                self.models[model_name].eval()
                
                self.primary_model = model_name
                logger.info(f"Model {model_name} loaded successfully on {self.device}")
            else:
                raise ValueError(f"Unknown model: {model_name}")
                
        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")
            raise
    
    def predict(self, text, language='en'):
        """
        Prédit la toxicité d'un texte
        
        Args:
            text (str): Texte à analyser
            language (str): Langue du texte
            
        Returns:
            dict: {
                'toxicity_score': float,
                'categories': list,
                'confidence': float,
                'probabilities': dict
            }
        """
        try:
            # Utiliser le modèle multilingue par défaut
            model = self.models[self.primary_model]
            tokenizer = self.tokenizers[self.primary_model]
            
            # Tokenisation
            inputs = tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=512,
                padding=True
            ).to(self.device)
            
            # Prédiction
            with torch.no_grad():
                outputs = model(**inputs)
                logits = outputs.logits
                
                # Appliquer sigmoid pour obtenir des probabilités
                probabilities = torch.sigmoid(logits).cpu().numpy()[0]
            
            # Construire le résultat
            result = {
                'probabilities': {},
                'categories': [],
                'toxicity_score': 0.0,
                'confidence': 0.0
            }
            
            # Seuil de détection par catégorie
            threshold = 0.5
            
            for i, label in enumerate(self.labels):
                prob = float(probabilities[i])
                result['probabilities'][label] = prob
                
                if prob >= threshold:
                    result['categories'].append(label)
            
            # Score de toxicité global (moyenne pondérée)
            weights = {
                'toxic': 1.0,
                'severe_toxic': 2.0,
                'obscene': 1.5,
                'threat': 2.0,
                'insult': 1.0,
                'identity_hate': 2.0
            }
            
            weighted_scores = [
                probabilities[i] * weights.get(label, 1.0)
                for i, label in enumerate(self.labels)
            ]
            
            result['toxicity_score'] = float(np.max(weighted_scores))
            result['confidence'] = float(np.mean(probabilities))
            
            return result
            
        except Exception as e:
            logger.error(f"Error during prediction: {str(e)}")
            raise
    
    def batch_predict(self, texts, languages=None):
        """Prédit la toxicité pour plusieurs textes"""
        results = []
        
        if languages is None:
            languages = ['en'] * len(texts)
        
        for text, lang in zip(texts, languages):
            try:
                result = self.predict(text, lang)
                results.append(result)
            except Exception as e:
                logger.error(f"Error predicting text: {str(e)}")
                results.append({
                    'error': str(e),
                    'toxicity_score': 0.0,
                    'categories': [],
                    'confidence': 0.0
                })
        
        return results
    
    def save_model(self, model_name=None):
        """Sauvegarde le modèle fine-tuné"""
        try:
            if model_name is None:
                model_name = self.primary_model
            
            model = self.models[model_name]
            tokenizer = self.tokenizers[model_name]
            
            save_path = self.model_dir / f"{model_name}_finetuned"
            save_path.mkdir(exist_ok=True)
            
            model.save_pretrained(str(save_path))
            tokenizer.save_pretrained(str(save_path))
            
            # Sauvegarder les métadonnées
            metadata = {
                'model_name': model_name,
                'labels': self.labels,
                'num_labels': self.num_labels,
                'device': str(self.device)
            }
            
            with open(save_path / 'metadata.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Model saved to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving model: {str(e)}")
            return False
    
    def is_loaded(self):
        """Vérifie si au moins un modèle est chargé"""
        return len(self.models) > 0
    
    def get_model_info(self):
        """Retourne les informations sur les modèles chargés"""
        return {
            'primary_model': self.primary_model,
            'loaded_models': list(self.models.keys()),
            'device': str(self.device),
            'labels': self.labels
        }
    
    