"""Обязательный список экстренных состояний из ТЗ: каждое должно прерывать опрос."""
import pytest

from app.domain.dialog import Status, evaluate
from app.domain.triage import CarePlace, Urgency, build_emergency
from tests.conftest import build_state, scenario

STRUCTURED_CASES = [
    ("CHEST_PAIN", {"complaint": ["pain"], "location": ["chest"]}),
    ("DYSPNEA_REST", {"complaint": ["breathing"], "location": ["dyspnea_rest"]}),
    ("LOSS_OF_CONSCIOUSNESS", {"complaint": ["neuro"], "location": ["fainting"]}),
    ("SEIZURES", {"complaint": ["neuro"], "location": ["seizure"]}),
    ("BLEEDING", {"complaint": ["gi"], "location": ["gi_blood"]}),
    ("STROKE", {"complaint": ["neuro"], "location": ["stroke_signs"]}),
    ("ANAPHYLAXIS", {"complaint": ["skin"], "location": ["face_swelling"]}),
    ("HEAD_TRAUMA_LOC", {"complaint": ["trauma"], "location": ["head_loc"]}),
    ("SUICIDAL", {"complaint": ["mental"], "location": ["self_harm"]}),
]


@pytest.mark.parametrize(("code", "answers"), STRUCTURED_CASES)
def test_structured_red_flag_interrupts_immediately(code, answers):
    evaluation = evaluate(build_state(answers))
    assert evaluation.status == Status.EMERGENCY
    assert code in {f.code for f in evaluation.red_flags}
    assert evaluation.question is None  # стандартный сценарий прерван


@pytest.mark.parametrize("option", ["chest", "dyspnea", "faint", "seizure", "bleeding", "fast", "anaphylaxis", "abdomen"])
def test_universal_danger_screen(option):
    state = build_state({"complaint": ["other"], "location": ["weakness"], "danger_signs": [option]})
    assert evaluate(state).status == Status.EMERGENCY


def test_acute_abdomen_by_severity():
    state = scenario(complaint=["pain"], location=["abdomen"], severity=["unbearable"])
    flags = {f.code for f in evaluate(state).red_flags}
    assert flags == {"ACUTE_ABDOMEN"}


def test_child_high_fever_is_emergency():
    state = build_state({"complaint": ["fever"], "location": ["t_very_high"], "danger_signs": ["none"],
                         "age_group": ["child"]})
    assert {f.code for f in evaluate(state).red_flags} == {"CHILD_HIGH_FEVER"}


def test_adult_high_fever_is_not_emergency():
    state = scenario(complaint=["fever"], location=["t_very_high"])
    assert evaluate(state).status == Status.COMPLETED


def test_child_high_fever_from_free_text():
    state = build_state({"complaint": "у ребенка температура 39,8 второй день", "location": ["t_unknown"],
                         "danger_signs": ["none"], "age_group": ["infant"]})
    assert "CHILD_HIGH_FEVER" in {f.code for f in evaluate(state).red_flags}


@pytest.mark.parametrize(("text", "code"), [
    ("Сильно давит в груди и отдаёт в руку", "CHEST_PAIN"),
    ("задыхаюсь даже лёжа", "DYSPNEA_REST"),
    ("мама потеряла сознание на кухне", "LOSS_OF_CONSCIOUSNESS"),
    ("у сына судороги", "SEIZURES"),
    ("кровь не останавливается после пореза", "BLEEDING"),
    ("перекосило лицо, речь невнятная", "STROKE"),
    ("после укуса осы отек горла", "ANAPHYLAXIS"),
    ("резкая боль в животе справа", "ACUTE_ABDOMEN"),
    ("ударился головой и был без сознания", "HEAD_TRAUMA_LOC"),
    ("не хочу жить", "SUICIDAL"),
])
def test_free_text_red_flags(text, code):
    state = build_state({"complaint": text})
    evaluation = evaluate(state)
    assert evaluation.status == Status.EMERGENCY
    assert code in {f.code for f in evaluation.red_flags}


def test_red_flag_in_later_free_text_interrupts():
    state = build_state({"complaint": ["skin"], "location": ["rash"], "danger_signs": "и ещё задыхаюсь"})
    assert evaluate(state).status == Status.EMERGENCY


def test_emergency_recommendation_routes_to_ambulance():
    flags = evaluate(build_state({"complaint": ["pain"], "location": ["chest"]})).red_flags
    rec = build_emergency(flags)
    assert rec.urgency == Urgency.EMERGENCY
    assert rec.care_place == CarePlace.AMBULANCE
    assert rec.rationale
