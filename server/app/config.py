"""Налаштування серверної частини, що зчитуються зі змінних середовища."""

from pathlib import Path
from typing import Literal

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

    # Фоновий виконавець таймерів (у тестах вимикається WORKER_ENABLED=false).
    worker_enabled: bool = True
    worker_interval_s: int = Field(default=5, ge=1)
    # Як часто виконувати очищення застарілих даних за тарифом.
    purge_interval_h: int = Field(default=24, ge=1)

    # Каталоги резервних копій і центру сертифікації (не в репозиторії).
    backup_dir: Path = Path("backups")
    ca_dir: Path = Path("ca")

    # Постачальник хронології інциденту: template (за замовчуванням) або
    # external (заглушка зовнішньої мовної моделі, реальних викликів немає).
    summary_provider: Literal["template", "external"] = "template"
    llm_api_url: str | None = None
    llm_model: str | None = None


settings = Settings()
