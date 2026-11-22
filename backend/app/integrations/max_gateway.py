"""Интеграция с мини-приложением MAX через core организаторов.

Схема входа:
1. Мини-приложение открывает наш URL с query-параметром ``token`` (JWT пользователя, живёт 5 минут).
2. Фронтенд сразу передаёт его на наш бэкенд (``POST /api/v1/integrations/max/auth``).
3. Бэкенд один раз вызывает core:
   ``GET {CORE_URL}/api/v3/users/user-for-external-service?token=<JWT>``
   с заголовком ``Authorization: Bearer <сервисный токен команды>``.
4. Из профиля берём только то, что нужно для маршрутизации: стабильный ``_id`` (хранится
   только как HMAC), возрастную группу (из даты рождения) и пол. Имя используется только
   для приветствия и не сохраняется. СНИЛС, полис ОМС, ФИО и телефон отбрасываются сразу.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

from ..config import get_settings

CORE_USER_PATH = "/api/v3/users/user-for-external-service"


class CoreError(Exception):
    """Базовая ошибка обращения к core."""


class CoreUnauthorized(CoreError):
    """401: пользовательский JWT пустой, битый или старше 5 минут."""


class CoreUserNotFound(CoreError):
    """404: подпись верная, но пользователя в core нет."""


class CoreUnavailable(CoreError):
    """Сеть, 5xx, 403 (неверный сервисный токен) или интеграция не настроена."""


@dataclass(frozen=True)
class CoreUser:
    """Минимальный профиль: только поля, нужные сервису. Остальное не покидает клиент core."""

    user_id: str
    birth_date: date | None
    sex: str | None  # "male" | "female" | None
    first_name: str | None  # только для приветствия, не сохраняется


def age_group(birth_date: date | None, today: date | None = None) -> str | None:
    if birth_date is None:
        return None
    today = today or date.today()
    years = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if years < 0:
        return None
    for limit, group in ((1, "infant"), (14, "child"), (18, "teen"), (50, "adult"), (65, "middle")):
        if years < limit:
            return group
    return "senior"


def _parse_user(data: dict) -> CoreUser:
    user_id = data.get("_id")
    if not user_id:
        raise CoreUnavailable("core вернул профиль без _id")
    try:
        birth = date.fromisoformat(data["birthDate"]) if data.get("birthDate") else None
    except (TypeError, ValueError):
        birth = None
    sex = {1: "male", 2: "female"}.get(data.get("sex"))
    first_name = ((data.get("full_name") or {}).get("firstName") or "").strip() or None
    return CoreUser(user_id=str(user_id), birth_date=birth, sex=sex, first_name=first_name)


class CoreClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 8.0,
                 transport: httpx.BaseTransport | None = None):
        self.url = base_url.rstrip("/") + CORE_USER_PATH  # без двойного слэша
        self.service_token = service_token
        self.timeout = timeout
        self.transport = transport

    def fetch_user(self, user_token: str) -> CoreUser:
        if not self.service_token:
            raise CoreUnavailable("CORE_SERVICE_TOKEN не задан")
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.get(
                    self.url,
                    params={"token": user_token},
                    headers={"Authorization": f"Bearer {self.service_token}"},
                )
        except httpx.HTTPError as exc:
            raise CoreUnavailable(f"core недоступен: {type(exc).__name__}") from exc

        if response.status_code == 401:
            raise CoreUnauthorized
        if response.status_code == 404:
            raise CoreUserNotFound
        if response.status_code != 200:
            raise CoreUnavailable(f"core ответил {response.status_code}")
        try:
            return _parse_user(response.json())
        except ValueError as exc:
            raise CoreUnavailable("core вернул некорректный JSON") from exc


def get_core_client() -> CoreClient:
    settings = get_settings()
    return CoreClient(settings.core_url, settings.core_service_token)
