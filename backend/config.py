from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Recall.ai
    recall_api_key: str = ""
    recall_region: str = "us-east-1"  # Recall.ai API region subdomain
    # Optional: sign the bot into Google so it can join sign-in-only meetings.
    # Set up a Google Login group in the Recall dashboard, then put its ID here.
    recall_google_login_group_id: str = ""

    # AssemblyAI
    assemblyai_api_key: str = ""
    assemblyai_speech_model: str = "universal-2"  # or "universal-3-pro"

    # Google Cloud
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gcs_bucket_name: str = ""
    google_application_credentials: str = ""

    # Vertex AI Vector Search
    vector_search_index_id: str = ""
    vector_search_endpoint_id: str = ""
    vector_search_deployed_index_id: str = ""

    # Models
    gemini_model: str = "gemini-2.5-pro"
    embedding_model: str = "text-embedding-004"

    # App
    webhook_base_url: str = ""  # public URL Recall.ai posts back to
    db_path: str = "meetings.db"
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
