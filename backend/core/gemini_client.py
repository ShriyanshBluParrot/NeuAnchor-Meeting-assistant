"""Gemini (Vertex AI) client factory.

Returns a fresh client per call. The underlying SDK client is not safe to reuse
across the concurrent worker threads we spawn (title/summary/notes run in
parallel), where a shared client's HTTP connection gets closed mid-use. Client
creation is cheap because google.auth caches the ADC token.
"""
from google import genai

from config import get_settings


def get_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
