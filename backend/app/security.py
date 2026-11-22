"""Защита данных: шифрование медицинских ответов, токены сессий, псевдонимизация."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from .config import get_cipher, get_settings


class EncryptedJSON(TypeDecorator):
    """JSON, который хранится в БД только в зашифрованном виде (Fernet: AES-128-CBC + HMAC-SHA256)."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        raw = json.dumps(value, ensure_ascii=False).encode()
        return get_cipher().encrypt(raw)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(get_cipher().decrypt(bytes(value)))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """В БД хранится только хеш токена: утечка БД не даёт доступа к сессиям."""
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


def pseudonymize(external_id: str) -> str:
    """HMAC от идентификатора пользователя мессенджера: исходный ID в БД не хранится."""
    key = get_settings().hash_salt.encode()
    return hmac.new(key, external_id.encode(), hashlib.sha256).hexdigest()
