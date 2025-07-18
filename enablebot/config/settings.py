"""
EnableBot Configuration Settings
Centralized configuration management
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "EnableBot"
    app_version: str = "3.0.0"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Database
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_service_key: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY")
    supabase_db_password: Optional[str] = os.getenv("SUPABASE_DB_PASSWORD")
    database_url: Optional[str] = os.getenv("DATABASE_URL")
    
    # AI Services
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Slack Configuration
    slack_client_id: Optional[str] = os.getenv("SLACK_CLIENT_ID")
    slack_client_secret: Optional[str] = os.getenv("SLACK_CLIENT_SECRET")
    slack_signing_secret: Optional[str] = os.getenv("SLACK_SIGNING_SECRET")
    slack_redirect_uri: str = os.getenv("SLACK_REDIRECT_URI", "http://localhost:8000/slack/oauth/callback")
    
    # Server Configuration
    host: str = os.getenv("HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8001"))
    web_port: int = int(os.getenv("WEB_PORT", "8000"))
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()