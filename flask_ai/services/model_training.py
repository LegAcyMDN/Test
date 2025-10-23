# model_training.py - Entraînement du modèle de modération
import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    TrainingArguments, 
    Trainer,
    EarlyStoppingCallback
)
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import json
from datetime import datetime


class ToxicityDataset(Dataset):
    """Dataset personnalisé pour la classification de toxicité"""
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            truncation=True,
            padding='max_length',
            max_length=self.max_length,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }


class ToxicityModel:
    def __init__(self, model_name='distilbert-base-multilingual-cased'):
        """
        Utilise DistilBERT multilingue pour supporter EN, FR, ES, DE
        Alternative : 'camembert-base' pour focus français
        """
        self.model_name = model_name
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"Utilisation du device : {self.device}")
        
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = None
        
    def prepare_data(self, df, test_size=0.2, val_size=0.1):
        """Prépare les données pour l'entraînement"""
        print("Préparation des données...")
        
        # Séparer features et labels
        X = df['text_clean'].values
        y = df['is_toxic'].values
        
        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Split train/validation
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=val_size, random_state=42, stratify=y_train
        )
        
        print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
        
        return X_train, X_val, X_test, y_train, y_val, y_test
    
    def create_datasets(self, X_train, X_val, X_test, y_train, y_val, y_test):
        """Crée les datasets PyTorch"""
        train_dataset = ToxicityDataset(X_train, y_train, self.tokenizer)
        val_dataset = ToxicityDataset(X_val, y_val, self.tokenizer)
        test_dataset = ToxicityDataset(X_test, y_test, self.tokenizer)
        
        return train_dataset, val_dataset, test_dataset
    
    def train(self, train_dataset, val_dataset, output_dir='./models/toxicity_model'):
        """Entraîne le modèle"""
        print("Initialisation du modèle...")
        
        # Charger le modèle
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name,
            num_labels=2,
            problem_type="single_label_classification"
        )
        self.model.to(self.device)
        
        # Arguments d'entraînement
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=3,
            per_device_train_batch_size=16,
            per_device_eval_batch_size=32,
            warmup_steps=500,
            weight_decay=0.01,
            logging_dir=f'{output_dir}/logs',
            logging_steps=100,
            eval_strategy="steps",
            eval_steps=500,
            save_strategy="steps",
            save_steps=500,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            save_total_limit=2,
            fp16=torch.cuda.is_available(),  # Mixed precision si GPU disponible
        )
        
        # Callbacks
        callbacks = [
            EarlyStoppingCallback(early_stopping_patience=3)
        ]
        
        # Trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            callbacks=callbacks,
        )
        
        # Entraînement
        print("Début de l'entraînement...")
        trainer.train()
        
        # Sauvegarder le modèle
        trainer.save_model(output_dir)
        self.tokenizer.save_pretrained(output_dir)
        
        print(f"Modèle sauvegardé dans : {output_dir}")
        
        return trainer
    
    def evaluate(self, test_dataset, model_path='./models/toxicity_model'):
        """Évalue le modèle sur le jeu de test"""
        print("Évaluation du modèle...")
        
        # Charger le modèle si nécessaire
        if self.model is None:
            self.load_model(model_path)
        
        self.model.eval()
        
        # Prédictions
        dataloader = DataLoader(test_dataset, batch_size=32)
        all_preds = []
        all_labels = []
        all_probs = []
        
        with torch.no_grad():
            for batch in dataloader:
                input_ids = batch['input_ids'].to(self.device)
                attention_mask = batch['attention_mask'].to(self.device)
                labels = batch['labels'].to(self.device)
                
                outputs = self.model(input_ids, attention_mask=attention_mask)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=1)
                preds = torch.argmax(logits, dim=1)
                
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                all_probs.extend(probs[:, 1].cpu().numpy())  # Proba classe toxique
        
        # Métriques
        print("\n" + "="*50)
        print("RAPPORT DE CLASSIFICATION")
        print("="*50)
        print(classification_report(all_labels, all_preds, 
                                   target_names=['Non-Toxique', 'Toxique']))
        
        print("\nMATRICE DE CONFUSION")
        print(confusion_matrix(all_labels, all_preds))
        
        # Sauvegarder les métriques
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'accuracy': np.mean(np.array(all_preds) == np.array(all_labels)),
            'predictions': {
                'total': len(all_preds),
                'toxic_predicted': int(np.sum(all_preds)),
                'toxic_actual': int(np.sum(all_labels))
            }
        }
        
        with open(f'{model_path}/evaluation_metrics.json', 'w') as f:
            json.dump(metrics, f, indent=2)
        
        return all_preds, all_probs, all_labels
    
    def load_model(self, model_path):
        """Charge un modèle sauvegardé"""
        print(f"Chargement du modèle depuis : {model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.to(self.device)
        self.model.eval()
    
    def predict(self, text):
        """Prédit la toxicité d'un texte"""
        if self.model is None:
            raise ValueError("Modèle non chargé. Utilisez load_model() d'abord.")
        
        # Tokenization
        inputs = self.tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=128,
            return_tensors='pt'
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Prédiction
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)
            pred = torch.argmax(probs, dim=1)
        
        return {
            'is_toxic': bool(pred.item()),
            'confidence': float(probs[0, pred.item()].item()),
            'toxic_probability': float(probs[0, 1].item()),
            'non_toxic_probability': float(probs[0, 0].item())
        }


# Script principal d'entraînement
if __name__ == "__main__":
    # Charger les données prétraitées
    df = pd.read_csv('./data/processed_dataset.csv')
    
    # Initialiser le modèle
    model = ToxicityModel(model_name='distilbert-base-multilingual-cased')
    
    # Préparer les données
    X_train, X_val, X_test, y_train, y_val, y_test = model.prepare_data(df)
    
    # Créer les datasets
    train_dataset, val_dataset, test_dataset = model.create_datasets(
        X_train, X_val, X_test, y_train, y_val, y_test
    )
    
    # Entraîner
    trainer = model.train(train_dataset, val_dataset)
    
    # Évaluer
    model.evaluate(test_dataset)
    
    # Test rapide
    test_texts = [
        "Hello, how are you?",
        "You are stupid and ugly!",
        "Bonjour, comment allez-vous?",
        "Tu es un idiot complet!"
    ]
    
    print("\n" + "="*50)
    print("TESTS DE PRÉDICTION")
    print("="*50)
    for text in test_texts:
        result = model.predict(text)
        print(f"\nTexte: {text}")
        print(f"Toxique: {result['is_toxic']} (confiance: {result['confidence']:.3f})")