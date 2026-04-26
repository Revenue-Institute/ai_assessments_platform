from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings (spec §16)."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "staging", "production"] = "local"

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # Auth
    jwt_signing_secret: str = ""
    session_cookie_secret: str = ""

    # Anthropic — split keys for cost attribution (spec §15).
    anthropic_api_key_generation: str = ""
    anthropic_api_key_scoring: str = ""

    # E2B
    e2b_api_key: str = ""

    # n8n
    n8n_host: str = ""
    n8n_admin_api_key: str = ""
    n8n_webhook_secret: str = ""

    # Redis
    upstash_redis_url: str = ""
    upstash_redis_token: str = ""

    # Email
    resend_api_key: str = ""
    resend_from_email: str = "assessments@revenueinstitute.com"

    # Embeddings
    voyage_api_key: str = ""
    openai_api_key: str = ""
    embedding_model: str = "voyage-3"
    embedding_dims: int = 1024

    # Observability
    sentry_dsn_api: str = ""
    axiom_token: str = ""
    axiom_dataset: str = ""

    # Storage
    supabase_storage_bucket_artifacts: str = "ri-artifacts"
    supabase_storage_bucket_references: str = "ri-references"

    # App URLs
    next_public_admin_url: str = "http://localhost:3000"
    next_public_candidate_url: str = "http://localhost:3001"
    internal_api_url: str = "http://localhost:8000"

    # Computed CORS origins
    cors_origins: list[str] = Field(default_factory=list)

    def resolve_cors_origins(self) -> list[str]:
        if self.cors_origins:
            return self.cors_origins
        return [self.next_public_admin_url, self.next_public_candidate_url]


@lru_cache
def get_settings() -> Settings:
    return Settings()
