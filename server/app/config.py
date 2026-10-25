"""Налаштування серверної частини, що зчитуються зі змінних середовища."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметри застосунку. Значення беруться зі змінних середовища або .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Обов'язкові параметри: задаються через DATABASE_URL та JWT_SECRET
    # (див. .env.example). Значень за замовчуванням немає навмисно.
    database_url: str
    jwt_secret: str = Field(min_length=32)

    jwt_algorithm: str = "HS256"
    # Короткоживучий токен доступу та довший токен оновлення (СЧ-1).
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    # Назва сервісу в застосунках-автентифікаторах (TOTP).
    totp_issuer: str = "Oberih"


settings = Settings()
