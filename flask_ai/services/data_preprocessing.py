# data_preprocessing.py - Nettoyage et préparation des datasets
import pandas as pd
import re
from unidecode import unidecode
from langdetect import detect, LangDetectException
import nltk
from nltk.corpus import stopwords

# Télécharger les stopwords si nécessaire
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)


class DataPreprocessor:
    def __init__(self):
        self.stop_words = {
            'en': set(stopwords.words('english')),
            'fr': set(stopwords.words('french')),
            'es': set(stopwords.words('spanish')),
            'de': set(stopwords.words('german'))
        }
    
    def clean_text(self, text):
        """Nettoie le texte en préservant le sens"""
        if pd.isna(text):
            return ""
        
        # Convertir en string
        text = str(text)
        
        # Supprimer les URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
        
        # Supprimer les mentions et hashtags Discord
        text = re.sub(r'<@!?\d+>|<@&\d+>|<#\d+>', '', text)
        
        # Remplacer les emojis Discord par espace
        text = re.sub(r'<a?:\w+:\d+>', ' ', text)
        
        # Supprimer les caractères spéciaux excessifs mais garder la ponctuation basique
        text = re.sub(r'[^\w\s\'\-àâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ.,!?]', ' ', text)
        
        # Réduire les espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        # Normaliser la casse (garder le texte original pour la détection)
        text = text.strip()
        
        return text
    
    def normalize_accents(self, text, remove_accents=False):
        """Normalise les accents"""
        if remove_accents:
            return unidecode(text)
        return text
    
    def detect_language(self, text):
        """Détecte la langue du texte"""
        try:
            if len(text.strip()) < 3:
                return 'unknown'
            lang = detect(text)
            return lang if lang in ['en', 'fr', 'es', 'de'] else 'other'
        except LangDetectException:
            return 'unknown'
    
    def load_and_merge_datasets(self, english_path, french_path):
        """Charge et fusionne les datasets anglais et français"""
        print("Chargement des datasets...")
        
        # Dataset anglais
        df_en = pd.read_csv(english_path)
        
        # Dataset français
        df_fr = pd.read_csv(french_path)
        
        # Uniformiser les colonnes pour le dataset anglais
        df_en_clean = pd.DataFrame({
            'text': df_en['comment_text'],
            'toxic': df_en['toxic'],
            'severe_toxic': df_en.get('severe_toxic', 0),
            'obscene': df_en.get('obscene', 0),
            'threat': df_en.get('threat', 0),
            'insult': df_en.get('insult', 0),
            'identity_hate': df_en.get('identity_hate', 0),
            'language': 'en'
        })
        
        # Uniformiser les colonnes pour le dataset français
        df_fr_clean = pd.DataFrame({
            'text': df_fr['comment_text'],
            'toxic': df_fr['toxic'],
            'severe_toxic': df_fr.get('severe_toxic', 0),
            'obscene': df_fr.get('obscene', 0),
            'threat': df_fr.get('threat', 0),
            'insult': df_fr.get('insult', 0),
            'identity_hate': df_fr.get('identity_hate', 0),
            'language': 'fr'
        })
        
        # Fusionner les datasets
        df_merged = pd.concat([df_en_clean, df_fr_clean], ignore_index=True)
        
        print(f"Dataset fusionné : {len(df_merged)} entrées")
        
        return df_merged
    
    def preprocess_dataset(self, df):
        """Prétraite le dataset complet"""
        print("Nettoyage des données...")
        
        # Supprimer les doublons
        initial_count = len(df)
        df = df.drop_duplicates(subset=['text'], keep='first')
        print(f"Doublons supprimés : {initial_count - len(df)}")
        
        # Supprimer les lignes avec texte vide
        df = df[df['text'].notna()]
        df = df[df['text'].str.strip() != '']
        
        # Nettoyer le texte
        print("Nettoyage du texte...")
        df['text_clean'] = df['text'].apply(self.clean_text)
        
        # Supprimer les lignes avec texte nettoyé vide
        df = df[df['text_clean'].str.strip() != '']
        
        # Vérifier/corriger la langue
        print("Détection de la langue...")
        df['detected_language'] = df['text_clean'].apply(self.detect_language)
        
        # Créer un label de toxicité global (au moins une catégorie toxique)
        toxicity_cols = ['toxic', 'severe_toxic', 'obscene', 'threat', 'insult', 'identity_hate']
        df['is_toxic'] = df[toxicity_cols].max(axis=1)
        
        # Calculer un score de sévérité (0-1)
        df['severity_score'] = df[toxicity_cols].mean(axis=1)
        
        print(f"Dataset final : {len(df)} entrées")
        print(f"Distribution toxique/non-toxique : {df['is_toxic'].value_counts().to_dict()}")
        
        return df
    
    def balance_dataset(self, df, ratio=2.0):
        """Équilibre le dataset (plus de négatifs que de positifs)"""
        toxic = df[df['is_toxic'] == 1]
        non_toxic = df[df['is_toxic'] == 0]
        
        # Échantillonner les non-toxiques
        target_non_toxic = int(len(toxic) * ratio)
        if len(non_toxic) > target_non_toxic:
            non_toxic = non_toxic.sample(n=target_non_toxic, random_state=42)
        
        df_balanced = pd.concat([toxic, non_toxic], ignore_index=True)
        df_balanced = df_balanced.sample(frac=1, random_state=42).reset_index(drop=True)
        
        print(f"Dataset équilibré : {len(df_balanced)} entrées")
        print(f"Ratio toxic/non-toxic : {len(toxic)}/{len(non_toxic)}")
        
        return df_balanced
    
    def save_processed_data(self, df, output_path):
        """Sauvegarde le dataset prétraité"""
        df.to_csv(output_path, index=False)
        print(f"Dataset sauvegardé : {output_path}")


# Script principal de préparation
if __name__ == "__main__":
    preprocessor = DataPreprocessor()
    
    # Chemins des datasets (à adapter)
    ENGLISH_DATASET = "./data/train.csv"
    FRENCH_DATASET = "./data/train_fr.csv"
    OUTPUT_PATH = "./data/processed_dataset.csv"
    
    # Charger et fusionner
    df = preprocessor.load_and_merge_datasets(ENGLISH_DATASET, FRENCH_DATASET)
    
    # Prétraiter
    df = preprocessor.preprocess_dataset(df)
    
    # Équilibrer
    df = preprocessor.balance_dataset(df, ratio=2.0)
    
    # Sauvegarder
    preprocessor.save_processed_data(df, OUTPUT_PATH)
    
    print("\nPrétraitement terminé !")
    print(f"Langues détectées : {df['detected_language'].value_counts().to_dict()}")
    print(f"Score de sévérité moyen (toxiques) : {df[df['is_toxic']==1]['severity_score'].mean():.3f}")