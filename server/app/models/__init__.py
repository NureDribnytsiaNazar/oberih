"""Моделі бази даних. Імпорт усіх модулів потрібен для реєстрації таблиць."""

from app.models import admin, devices, enums, events, facilities, users
from app.models.base import Base

__all__ = ["Base", "admin", "devices", "enums", "events", "facilities", "users"]
