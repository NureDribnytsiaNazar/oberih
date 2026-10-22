"""Налаштування серверної частини, що зчитуються зі змінних середовища."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметри застосунку. Значення беруться зі змінних середовища або .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Обов'язковий параметр: задається через DATABASE_URL (див. .env.example).
    database_url: str


settings = Settings()
