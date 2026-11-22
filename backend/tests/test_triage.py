"""Маршрутизация: специалист, срочность, место обращения, обоснование, безопасность."""
import re

import pytest

from app.domain.dialog import Status, evaluate
from app.domain.triage import CarePlace, Urgency, build_recommendation
from tests.conftest import scenario


def rec(**overrides):
    state = scenario(**overrides)
    assert evaluate(state).status == Status.COMPLETED
    return build_recommendation(state)


def test_mild_recent_runny_nose_is_self_care():
    r = rec()
    assert r.urgency == Urgency.SELF_CARE
    assert r.care_place == CarePlace.PHARMACY
    assert CarePlace.TELEMEDICINE in r.alternatives
    assert r.specialty.startswith("Оториноларинголог")


def test_risk_factor_blocks_self_care():
    r = rec(chronic=["asthma"])
    assert r.urgency == Urgency.PLANNED
    assert any("хронических" in a for a in r.advice)


def test_severe_symptoms_are_urgent():
    r = rec(complaint=["pain"], location=["back"], severity=["severe"])
    assert r.urgency == Urgency.URGENT
    assert r.specialty == "Невролог"
    assert r.care_place == CarePlace.CLINIC


def test_trauma_goes_to_emergency_room():
    r = rec(complaint=["trauma"], location=["limb"], severity=["moderate"])
    assert r.urgency == Urgency.URGENT
    assert r.care_place == CarePlace.ER
    assert r.specialty == "Травматолог"


def test_child_gets_pediatrician():
    r = rec(complaint=["fever"], location=["t_mid"], age_group=["child"], severity=["moderate"])
    assert r.specialty == "Педиатр"


def test_infant_fever_is_urgent():
    r = rec(complaint=["fever"], location=["t_mid"], age_group=["infant"])
    assert r.urgency == Urgency.URGENT


def test_long_fever_is_urgent():
    r = rec(complaint=["fever"], location=["t_high"], duration=["d4_7"], severity=["moderate"])
    assert r.urgency == Urgency.URGENT


def test_pregnancy_raises_urgency():
    r = rec(complaint=["gi"], location=["nausea"], sex=["female"], pregnancy=["pregnant"], severity=["moderate"])
    assert r.urgency == Urgency.URGENT
    assert any("беременност" in a for a in r.advice)


def test_chronic_complaint_is_planned():
    r = rec(complaint=["skin"], location=["mole"], duration=["gt30"])
    assert r.urgency == Urgency.PLANNED
    assert r.care_place == CarePlace.CLINIC
    assert r.specialty == "Дерматолог"


@pytest.mark.parametrize(("complaint", "location", "specialty"), [
    ("pain", "head", "Невролог"),
    ("pain", "teeth", "Стоматолог"),
    ("gi", "heartburn", "Гастроэнтеролог"),
    ("eyes", "vision_gradual", "Офтальмолог"),
    ("mental", "anxiety", "Психиатр или психотерапевт"),
    ("trauma", "cut", "Хирург"),
    ("other", "urination", "Уролог"),
])
def test_specialty_mapping(complaint, location, specialty):
    assert rec(complaint=[complaint], location=[location]).specialty == specialty


def test_rationale_lists_symptoms():
    r = rec(complaint=["pain"], location=["head"], severity=["moderate"])
    joined = " ".join(r.rationale)
    assert "боль" in joined and "голова" in joined and "умеренно" in joined


FORBIDDEN = re.compile(r"\b(мг|мл|таблет\w*|капсул\w*|диагноз:|парацетамол|ибупрофен|антибиотик\w*)\b", re.I)


@pytest.mark.parametrize("overrides", [
    {},
    {"complaint": ["fever"], "location": ["t_mid"]},
    {"complaint": ["pain"], "location": ["joints"], "severity": ["severe"]},
    {"complaint": ["gi"], "location": ["diarrhea"]},
])
def test_no_medication_or_diagnosis_in_output(overrides):
    r = rec(**overrides)
    text = " ".join([r.specialty, *r.rationale, *r.advice])
    assert not FORBIDDEN.search(text)
