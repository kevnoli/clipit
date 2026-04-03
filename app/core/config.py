from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Clipit", alias="APP_NAME")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    app_base_url: str = Field(default="", alias="APP_BASE_URL")
    session_secret: str = Field(default="", alias="SESSION_SECRET")
    secret_encryption_key: str = Field(default="", alias="SECRET_ENCRYPTION_KEY")
    twitch_client_id: str = Field(default="", alias="TWITCH_CLIENT_ID")
    twitch_client_secret: str = Field(default="", alias="TWITCH_CLIENT_SECRET")
    twitch_redirect_path: str = Field(
        default="/api/auth/twitch/callback",
        alias="TWITCH_REDIRECT_PATH",
    )
    database_url: str = Field(default="sqlite:///clipitbot.db", alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    @property
    def twitch_redirect_uri(self) -> str:
        return f"{self.app_base_url.rstrip('/')}{self.twitch_redirect_path}"

    @property
    def session_cookie_secure(self) -> bool:
        return self.app_base_url.startswith("https://")

    @property
    def csrf_cookie_name(self) -> str:
        return "clipit_csrf"

    @property
    def oauth_state_cookie_name(self) -> str:
        return "clipit_oauth"

    def validate_runtime_settings(self):
        required_fields = {
            "APP_BASE_URL": self.app_base_url,
            "SESSION_SECRET": self.session_secret,
            "SECRET_ENCRYPTION_KEY": self.secret_encryption_key,
            "TWITCH_CLIENT_ID": self.twitch_client_id,
            "TWITCH_CLIENT_SECRET": self.twitch_client_secret,
        }
        missing = [name for name, value in required_fields.items() if not value.strip()]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required settings: {joined}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
