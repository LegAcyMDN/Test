# config.py - Configuration Flask
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # IA
    MODEL_PATH = os.getenv('MODEL_PATH', './models/')
    CONFIDENCE_HIGH = float(os.getenv('CONFIDENCE_HIGH', 0.9))
    CONFIDENCE_LOW = float(os.getenv('CONFIDENCE_LOW', 0.5))
    
    # Limites
    MAX_MESSAGE_LENGTH = int(os.getenv('MAX_MESSAGE_LENGTH', 2000))
    MIN_MESSAGE_LENGTH = int(os.getenv('MIN_MESSAGE_LENGTH', 3))
    MAX_REQUESTS_PER_MINUTE = int(os.getenv('MAX_REQUESTS_PER_MINUTE', 60))
    
    # Logs
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', 90))
    LOCAL_BACKUP_PATH = os.getenv('LOCAL_BACKUP_PATH', './backups/')
    
    # RGPD
    ANONYMIZE_LOGS = os.getenv('ANONYMIZE_LOGS', 'True').lower() == 'true'