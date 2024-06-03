import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Base configuration, common to all environments
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'json'}  # Add allowed file extensions
    MAX_CONTENT_LENGTH = 70 * 1024 * 1024  # 70MB max upload size
    GOOGLE_AI_API_KEY = os.environ.get("GOOGLE_AI_API_KEY")


class DevelopmentConfig(Config):
    # Development-specific settings (e.g., debug mode)
    DEBUG = False


class TestingConfig(Config):
    # Testing-specific settings
    TESTING = False
    # Example: Use an in-memory SQLite database for testing
    # SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ProductionConfig(Config):
    # Production-specific settings (e.g., more secure defaults)
    DEBUG = False


# Dictionary to easily access different configurations
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,

    # Set the default configuration here
    'default': DevelopmentConfig
}
