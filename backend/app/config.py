"""Настройки приложения из переменных окружения (12-factor)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache

from cryptography.fernet import Fernet

log = logging.getLogger(__name__)


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]

def _safe_int(value: str, default: int) -> int:
    """Безопасное приведение к int с фоллбэком."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./medmarshrut.db"))
    data_encryption_key: str = field(default_factory=lambda: os.getenv("DATA_ENCRYPTION_KEY", ""))
    hash_salt: str = field(default_factory=lambda: os.getenv("HASH_SALT", "dev-only-salt"))
    session_ttl_hours: int = field(default_factory=lambda: _safe_int(os.getenv("SESSION_TTL_HOURS", "24"), 24))
    purge_interval_minutes: int = field(default_factory=lambda: _safe_int(os.getenv("PURGE_INTERVAL_MINUTES", "30"), 30))
    core_url: str = field(default_factory=lambda: os.getenv("CORE_URL", "https://tm-test-yakut.hostco.ru"))
    core_service_token: str = field(default_factory=lambda: os.getenv("CORE_SERVICE_TOKEN", ""))
    cors_origins: list[str] = field(default_factory=lambda: _list(os.getenv("CORS_ORIGINS", "http://localhost:5173")))


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_cipher() -> Fernet:
    key = get_settings().data_encryption_key
    if not key:
        log.warning("DATA_ENCRYPTION_KEY не задан: используется временный ключ, данные не переживут перезапуск")
        key = Fernet.generate_key().decode()
    return Fernet(key.encode())
