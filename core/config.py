from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Upie AI Intelligence"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Postgres Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "fios_db"
    POSTGRES_PORT: str = "5432"
    
    DATABASE_URL: Optional[str] = None
    
    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
             url = self.DATABASE_URL
             if url.startswith("postgres://"):
                 url = url.replace("postgres://", "postgresql+asyncpg://", 1)
             elif url.startswith("postgresql://"):
                 url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
             return url
        
        import os
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fios_local_db.sqlite3")
        return f"sqlite+aiosqlite:///{os.path.abspath(db_path)}"
    
    # Vector DB (ChromaDB)
    CHROMA_PERSIST_DIRECTORY: str = "./chroma_data"
    
    # Security
    SECRET_KEY: str = "UPDATE_THIS_SECRET_KEY_FOR_PRODUCTION"
    
    # AI/LLM Keys
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # External Agent Webhooks
    OPENCLAW_WEBHOOK_URL: Optional[str] = None
    
    model_config = SettingsConfigDict(env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"), case_sensitive=True, extra="ignore")

settings = Settings()
