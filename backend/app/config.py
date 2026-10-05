import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)
_PLACEHOLDER_SECRETS = {"dev-secret-change-me", "replace-with-64-random-chars", "change-me", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://ekcode:ekcode@localhost:5432/ekcode"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_minutes: int = 720
    cookie_secure: bool = False
    admin_email: str = "admin@ekcode.local"
    admin_password: str = "ChangeMe@2026"
    data_dir: str = "/data"
    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_mb: int = 100
    stale_job_minutes: int = 30          # a queued/running job with no progress for this long can be restarted
    docs_enabled: bool = True            # set DOCS_ENABLED=false to hide /api/docs in production
    log_level: str = "INFO"
    sap_base_url: str = ""
    sap_api_key: str = ""


settings = Settings()


def check_secrets() -> None:
    """Refuse a guessable JWT secret when running behind HTTPS (production); only warn in local dev."""
    weak = settings.jwt_secret in _PLACEHOLDER_SECRETS or len(settings.jwt_secret) < 32
    if weak and settings.cookie_secure:
        raise RuntimeError('JWT_SECRET is weak. Generate one: python -c "import secrets; print(secrets.token_hex(32))"')
    if weak:
        log.warning("JWT_SECRET is weak: acceptable for local development only")
