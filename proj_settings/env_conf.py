from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret_key: str
    jwt_secret_refresh_key: str
    client_id: str
    client_sec: str
    redirect_uri: str
    db_pass: str
    db_schema: str
    db_user: str
    db_host: str = "localhost"
    user_scopes: list[str]

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = []

    # Кука: домен-родитель для доступа с поддоменов (напр. .kirirpy.tech).
    # None — host-only (локальная разработка). secure включать только под HTTPS.
    cookie_domain: str | None = None
    cookie_secure: bool = False


settings = Settings()
