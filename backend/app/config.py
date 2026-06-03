"""Application settings loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Centumhi License Hub"
    environment: str = "dev"  # dev | prod
    api_prefix: str = "/api"

    # Database
    database_url: str = "sqlite:///./license_hub.db"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14

    # Seed admin (consumed only by app.scripts.seed_admin)
    seed_admin_email: str = "admin@centumhi.co.kr"
    seed_admin_password: str = "change-this-password"
    seed_admin_name: str = "관리자"

    # CORS — comma separated whitelist (parsed via cors_origins_list)
    cors_origins: str = "http://localhost:3000"

    # Bot verify endpoint replay protection (seconds of allowed clock skew)
    verify_timestamp_tolerance_sec: int = 300

    # Scheduler / notifications
    scheduler_enabled: bool = True
    expiry_notify_days: int = 3

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
