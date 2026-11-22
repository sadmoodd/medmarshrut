import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DATA_ENCRYPTION_KEY", "q2qYb3SXfVdHWv2M8kM8l0b7O7j9e8bKXqgK2P1cZ0Y=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.domain.dialog import Answer, DialogState, next_question, validate_answer
from app.main import app

# Полный «спокойный» сценарий: взрослый, лёгкий насморк 1–3 дня.
CALM = {
    "complaint": ["breathing"],
    "location": ["runny_nose"],
    "danger_signs": ["none"],
    "age_group": ["adult"],
    "sex": ["male"],
    "duration": ["d1_3"],
    "severity": ["mild"],
    "chronic": ["none"],
    "medications": ["none"],
    "allergies": ["none"],
    "surgeries": ["no"],
    "heredity": ["none"],
    "pregnancy": ["no"],
    "habits": ["none"],
}


def build_state(answers: dict) -> DialogState:
    """Проводит ответы через валидацию в порядке диалога (как реальный пользователь)."""
    state = DialogState()
    while (question := next_question(state)) is not None and question.id in answers:
        value = answers[question.id]
        if isinstance(value, str):
            answer = validate_answer(state, question.id, [], value)
        else:
            answer = validate_answer(state, question.id, value, None)
        state.answers[question.id] = answer
    return state


def scenario(**overrides) -> DialogState:
    return build_state({**CALM, **overrides})


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    test_client = TestClient(app)
    test_client.engine = engine
    test_client.session_factory = TestSession
    yield test_client
    app.dependency_overrides.clear()


__all__ = ["Answer", "CALM", "build_state", "scenario"]
