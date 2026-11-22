"""Вход из мини-приложения MAX: клиент core, минимизация данных профиля, предзаполнение."""
from datetime import date

import httpx
import pytest
from sqlalchemy import text

from app.integrations.max_gateway import (
    CoreClient,
    CoreUnauthorized,
    CoreUnavailable,
    CoreUserNotFound,
    age_group,
    get_core_client,
)
from app.main import app

PROFILE = {
    "_id": "63199dcd77dad20024a74628",
    "birthDate": "1987-10-26",
    "sex": 2,
    "SNILS": "16067057157",
    "OMS": {"number": "34635345"},
    "full_name": {"lastName": "Иванова", "firstName": "Мария", "middleName": "Ивановна"},
    "phone": "71234567890",
}


def core_with(status: int, payload=None, seen: list | None = None) -> CoreClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload if payload is not None else {})

    return CoreClient("https://core.example/", "service-secret", transport=httpx.MockTransport(handler))


# --- клиент core ----------------------------------------------------------------
def test_core_request_format():
    seen = []
    user = core_with(200, PROFILE, seen).fetch_user("user.jwt.token")
    request = seen[0]
    assert str(request.url).startswith("https://core.example/api/v3/users/user-for-external-service?")
    assert "//api" not in str(request.url)
    assert request.url.params["token"] == "user.jwt.token"
    assert request.headers["Authorization"] == "Bearer service-secret"
    assert user.user_id == PROFILE["_id"]
    assert user.sex == "female" and user.birth_date == date(1987, 10, 26) and user.first_name == "Мария"
    assert not hasattr(user, "SNILS") and not hasattr(user, "phone")


@pytest.mark.parametrize(("status", "error"), [
    (401, CoreUnauthorized), (404, CoreUserNotFound), (403, CoreUnavailable), (500, CoreUnavailable),
])
def test_core_errors(status, error):
    with pytest.raises(error):
        core_with(status).fetch_user("user.jwt.token")


def test_core_without_service_token_is_unavailable():
    with pytest.raises(CoreUnavailable):
        CoreClient("https://core.example", "").fetch_user("user.jwt.token")


@pytest.mark.parametrize(("birth", "group"), [
    (date(2026, 6, 1), "infant"), (date(2020, 1, 1), "child"), (date(2010, 1, 1), "teen"),
    (date(1987, 10, 26), "adult"), (date(1970, 1, 1), "middle"), (date(1950, 1, 1), "senior"), (None, None),
])
def test_age_group(birth, group):
    assert age_group(birth, today=date(2026, 11, 22)) == group


# --- эндпоинт входа -------------------------------------------------------------
@pytest.fixture()
def max_login(client):
    def login(status=200, payload=PROFILE):
        app.dependency_overrides[get_core_client] = lambda: core_with(status, payload)
        return client.post("/api/v1/integrations/max/auth", json={"token": "user.jwt.token"})
    return login


def test_login_creates_session_and_asks_for_whom(client, max_login):
    r = max_login()
    assert r.status_code == 201
    body = r.json()
    assert body["greeting_name"] == "Мария"
    assert body["question"]["id"] == "for_whom"


def test_profile_pii_is_not_stored(client, max_login):
    body = max_login().json()
    headers = {"X-Session-Token": body["session_token"]}
    client.post(f"/api/v1/sessions/{body['session_id']}/answers", headers=headers,
                json={"step_id": "for_whom", "option_ids": ["self"]})
    with client.engine.connect() as conn:
        dump = b"".join(
            str(value).encode() if not isinstance(value, (bytes, memoryview)) else bytes(value)
            for table in ("patient_sessions", "session_answers")
            for row in conn.execute(text(f"SELECT * FROM {table}"))
            for value in row
        )
    for secret in ("16067057157", "34635345", "71234567890", "Мария", "Иванова", PROFILE["_id"], "1987"):
        assert secret.encode() not in dump


def test_self_prefills_age_and_sex_and_back_undoes_it(client, max_login):
    body = max_login().json()
    sid, headers = body["session_id"], {"X-Session-Token": body["session_token"]}
    state = client.post(f"/api/v1/sessions/{sid}/answers", headers=headers,
                        json={"step_id": "for_whom", "option_ids": ["self"]}).json()
    assert state["question"]["id"] == "complaint"
    answers = {h["step_id"]: h["answer"] for h in state["history"]}
    assert answers["age_group"] == "18–49 лет (из профиля MAX)"
    assert answers["sex"] == "Женский (из профиля MAX)"

    state = client.post(f"/api/v1/sessions/{sid}/back", headers=headers).json()
    assert state["question"]["id"] == "for_whom" and state["history"] == []


def test_other_person_asks_age_and_sex(client, max_login):
    body = max_login().json()
    sid, headers = body["session_id"], {"X-Session-Token": body["session_token"]}
    client.post(f"/api/v1/sessions/{sid}/answers", headers=headers,
                json={"step_id": "for_whom", "option_ids": ["other"]})
    for step, option in (("complaint", "fever"), ("location", "t_very_high"), ("danger_signs", "none")):
        state = client.post(f"/api/v1/sessions/{sid}/answers", headers=headers,
                            json={"step_id": step, "option_ids": [option]}).json()
    assert state["question"]["id"] == "age_group"  # возраст ребёнка спрашиваем, а не берём из профиля
    state = client.post(f"/api/v1/sessions/{sid}/answers", headers=headers,
                        json={"step_id": "age_group", "option_ids": ["child"]}).json()
    assert state["status"] == "emergency"


@pytest.mark.parametrize(("status", "expected"), [(401, 401), (404, 404), (403, 502), (500, 502)])
def test_login_errors(max_login, status, expected):
    assert max_login(status=status).status_code == expected
