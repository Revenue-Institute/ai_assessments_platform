from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Minimum length we require for HMAC / signing secrets outside local dev.
# 32 bytes is the conventional floor for HS256-style secrets (OWASP and
# RFC 7518 §3.2 both call out >= 256 bits / 32 bytes for keyed-MAC inputs).
_MIN_SECRET_LEN = 32


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
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # Supabase project's auth.jwt_secret (HS256)
    database_url: str = ""

    # Auth
    jwt_signing_secret: str = ""
    session_cookie_secret: str = ""

    # Anthropic, split keys for cost attribution (spec §15).
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
    # Dedicated sending subdomain (go.revenueinstitute.com) verified in
    # Resend, kept off the apex so transactional sends don't share the
    # primary Google Workspace mail reputation. Override per env via
    # RESEND_FROM_EMAIL; an optional display name is allowed, e.g.
    # "Revenue Institute <assessments@go.revenueinstitute.com>".
    resend_from_email: str = "assessments@go.revenueinstitute.com"
    resend_webhook_secret: str = ""

    # Embeddings (v1 uses OpenAI text-embedding-3-small @ 1024 dims via
    # the dimensions parameter; reference_chunks.embedding is vector(1024)
    # per migration 0004).
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
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

    # Trusted reverse proxies (spec §10, §18: do not honor X-Forwarded-For
    # unless the immediate peer is one of these). Stored as a raw
    # comma-separated string from env (pydantic-settings tries to JSON-
    # parse list-typed fields before validators run, which fails for the
    # natural "1.2.3.4,5.6.7.8" form); accessor below exposes the parsed
    # list. Defaults to empty so the unsafe header is ignored when no
    # proxy is configured.
    trusted_proxy_ips_raw: str = Field(default="", alias="TRUSTED_PROXY_IPS")

    @property
    def trusted_proxy_ips(self) -> list[str]:
        return [item.strip() for item in (self.trusted_proxy_ips_raw or "").split(",") if item.strip()]

    def resolve_cors_origins(self) -> list[str]:
        if self.cors_origins:
            return self.cors_origins
        return [self.next_public_admin_url, self.next_public_candidate_url]

    @model_validator(mode="after")
    def _require_secrets_outside_local(self) -> "Settings":
        """Spec §18 + CLAUDE.md: fail closed on misconfigured secrets so
        a non-local deploy can never start with an empty or weak signing
        key. Local dev is tolerated so contributors can run the API
        without ceremony; staging and production must satisfy >= 32 chars."""

        if self.app_env == "local":
            return self
        for name in ("jwt_signing_secret", "session_cookie_secret"):
            value = getattr(self, name) or ""
            if not value:
                raise ValueError(
                    f"{name.upper()} is required when APP_ENV={self.app_env!r}."
                )
            if len(value) < _MIN_SECRET_LEN:
                raise ValueError(
                    f"{name.upper()} must be at least {_MIN_SECRET_LEN} characters "
                    f"when APP_ENV={self.app_env!r}."
                )
        return self

    @model_validator(mode="after")
    def _validate_service_urls(self) -> "Settings":
        """Sanity-check externally-visible URLs in non-local envs. We do
        not assert reachability (that is for /health/ready), only that
        the operator did not paste an obvious typo (http instead of
        https, missing scheme, etc). Local dev is tolerated so a
        contributor can point at a local Supabase or skip secrets entirely."""

        if self.app_env == "local":
            return self
        if self.supabase_url and not self.supabase_url.startswith("https://"):
            raise ValueError(
                "SUPABASE_URL must start with https:// in non-local environments."
            )
        if self.database_url and not self.database_url.startswith(
            ("postgresql://", "postgres://")
        ):
            raise ValueError(
                "DATABASE_URL must use postgresql:// or postgres:// scheme."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
