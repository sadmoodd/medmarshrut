"""Сквозные сценарии через HTTP API и проверки безопасности хранения."""
from datetime import timedelta

from sqlalchemy import text

from app.models import PatientSession, utcnow
from app.services import purge_expired
from tests.conftest import CALM


def start(client):
    r = client.post("/api/v1/sessions", json={"channel": "web"})
    assert r.status_code == 201
    body = r.json()
    return body, {"X-Session-Token": body["session_token"]}


def answer(client, sid, headers, step, ids=(), text_=None, skip=False):
    return client.post(f"/api/v1/sessions/{sid}/answers", headers=headers,
                       json={"step_id": step, "option_ids": list(ids), "text": text_, "skip": skip})


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_start_shows_disclaimer_and_first_question(client):
    body, _ = start(client)
    assert "не ставит диагноз" in body["disclaimer_start"]
    assert body["question"]["id"] == "complaint"
    assert body["progress"]["answered"] == 0
    assert body["can_go_back"] is False


def test_full_dialog_returns_recommendation_card(client):
    body, headers = start(client)
    sid = body["session_id"]
    state = body
    while state["status"] == "active":
        step = state["question"]["id"]
        state = answer(client, sid, headers, step, CALM[step]).json()
    assert state["status"] == "completed"
    card = state["recommendation"]
    assert card["urgency"] == "self_care"
    assert card["specialty"] and card["care_place_label"] and card["rationale"]
    assert "скорую" in state["disclaimer_end"]
    assert state["progress"]["percent"] == 100
    assert len(state["history"]) == 13


def test_emergency_interrupts_and_back_restores(client):
    body, headers = start(client)
    sid = body["session_id"]
    answer(client, sid, headers, "complaint", ["pain"])
    state = answer(client, sid, headers, "location", ["chest"]).json()
    assert state["status"] == "emergency"
    assert "103" in state["emergency"]["message"]
    assert state["recommendation"]["care_place"] == "ambulance"
    assert any("Не дожидайтесь" in a for a in state["emergency"]["advice"])

    # Дальше отвечать нельзя, но можно вернуться, если ответ выбран ошибочно.
    assert answer(client, sid, headers, "danger_signs", ["none"]).status_code == 409
    state = client.post(f"/api/v1/sessions/{sid}/back", headers=headers).json()
    assert state["status"] == "active" and state["question"]["id"] == "location"
    assert state["recommendation"] is None


def test_free_text_complaint(client):
    body, headers = start(client)
    state = answer(client, body["session_id"], headers, "complaint", text_="болит горло").json()
    assert state["question"]["id"] == "location"
    assert "Ухо, горло, нос" in state["history"][0]["answer"]


def test_validation_error_is_422(client):
    body, headers = start(client)
    r = answer(client, body["session_id"], headers, "complaint", ["no_such_option"])
    assert r.status_code == 422


def test_token_is_required(client):
    body, _ = start(client)
    sid = body["session_id"]
    assert client.get(f"/api/v1/sessions/{sid}").status_code == 403
    assert client.get(f"/api/v1/sessions/{sid}", headers={"X-Session-Token": "wrong"}).status_code == 403
    assert client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000",
                      headers={"X-Session-Token": "x"}).status_code == 404


def test_user_can_delete_own_data(client):
    body, headers = start(client)
    sid = body["session_id"]
    answer(client, sid, headers, "complaint", ["pain"])
    assert client.delete(f"/api/v1/sessions/{sid}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/sessions/{sid}", headers=headers).status_code == 404
    with client.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM session_answers")).scalar() == 0


def test_answers_are_encrypted_at_rest(client):
    body, headers = start(client)
    answer(client, body["session_id"], headers, "complaint", text_="болит горло")
    with client.engine.connect() as conn:
        raw = conn.execute(text("SELECT payload FROM session_answers")).scalar()
        token_hash = conn.execute(text("SELECT token_hash FROM patient_sessions")).scalar()
    assert "горло".encode() not in bytes(raw)
    assert token_hash != body["session_token"]


def test_expired_sessions_are_purged(client):
    body, headers = start(client)
    with client.session_factory() as db:
        session = db.get(PatientSession, __import__("uuid").UUID(body["session_id"]))
        session.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert purge_expired(db) == 1
    assert client.get(f"/api/v1/sessions/{body['session_id']}", headers=headers).status_code == 404


def test_api_responses_are_not_cached(client):
    assert client.get("/api/v1/health").headers["Cache-Control"] == "no-store"
