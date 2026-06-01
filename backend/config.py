from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AssemblyAI
    assemblyai_api_key: str = ""
    assemblyai_speech_model: str = "universal-2"  # or "universal-3-pro"

    # MongoDB Atlas
    mongo_uri: str = ""
    mongo_db_name: str = "meeting_assistant"

    # Gemini (Google AI Studio API key)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"

    # App
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
