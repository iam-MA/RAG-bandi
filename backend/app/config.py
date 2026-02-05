"""
Application Configuration
Loads and validates environment variables using pydantic-settings
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        supabase_url: Supabase project URL
        supabase_key: Supabase service role key (bypasses RLS)
        api_host: Host to bind the API server
        api_port: Port to bind the API server
        debug: Enable debug mode
    """
    
    # Supabase Configuration (required)
    supabase_url: str
    supabase_key: str
    
    # OpenAI Configuration (required for embeddings)
    openai_api_key: str
    
    # LlamaParse Configuration (for tender document parsing)
    llama_cloud_api_key: str
    
    # API Configuration (optional with defaults)
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False
    
    # Project metadata
    project_name: str = "AI Tender Architect"
    version: str = "0.1.0"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns cached Settings instance.
    Uses lru_cache to avoid re-reading .env file on every call.
    """
    return Settings()
