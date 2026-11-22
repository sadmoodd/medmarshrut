"""Движок диалога: порядок шагов, условия, прогресс, валидация, анализ текста."""
import pytest

from app.domain import text_analysis
from app.domain.dialog import DialogError, DialogState, evaluate, next_question, validate_answer
from tests.conftest import CALM, build_state, scenario


def test_first_question_is_complaint_with_free_text():
    q = next_question(DialogState())
    assert q.id == "complaint" and q.allow_text


def test_location_depends_on_category():
    q = next_question(build_state({"complaint": ["fever"]}))
    assert q.id == "location"
    assert "температура" in q.text.lower()


def test_pregnancy_asked_only_for_fertile_women():
    men = scenario()
    assert "pregnancy" not in men.answers  # мужчине вопрос не задаётся
    assert evaluate(men).status.value == "completed"

    women = build_state({**{k: v for k, v in CALM.items() if k not in {"pregnancy", "habits"}}, "sex": ["female"]})
    assert next_question(women).id == "pregnancy"

    senior = build_state({**{k: v for k, v in CALM.items() if k not in {"pregnancy", "habits"}},
                          "sex": ["female"], "age_group": ["senior"]})
    assert next_question(senior).id == "habits"


def test_habits_skipped_for_children_and_optional_for_adults():
    child = build_state({**{k: v for k, v in CALM.items() if k != "habits"}, "age_group": ["child"]})
    assert evaluate(child).status.value == "completed"

    adult = build_state({k: v for k, v in CALM.items() if k != "habits"})
    answer = validate_answer(adult, "habits", [], None, skip=True)
    assert answer.skipped


def test_progress_counts_applicable_steps():
    e = evaluate(build_state({"complaint": ["pain"], "location": ["head"]}))
    assert e.answered == 2
    assert e.total == 14
    male = evaluate(build_state({k: CALM[k] for k in list(CALM)[:5]}))
    assert male.total == 13  # вопрос о беременности отпал


@pytest.mark.parametrize(("step", "ids", "text", "message"), [
    ("location", ["head"], None, "не к текущему"),
    ("complaint", ["unknown"], None, "неизвестный"),
    ("complaint", [], None, "Выберите"),
    ("complaint", ["pain", "fever"], None, "только один"),
    ("complaint", [], "x" * 501, "слишком длинный"),
])
def test_validation_errors(step, ids, text, message):
    with pytest.raises(DialogError, match=message):
        validate_answer(DialogState(), step, ids, text)


def test_exclusive_option_cannot_be_combined():
    state = build_state({"complaint": ["pain"], "location": ["head"]})
    with pytest.raises(DialogError, match="нельзя совмещать"):
        validate_answer(state, "danger_signs", ["none", "chest"], None)


def test_required_question_cannot_be_skipped():
    with pytest.raises(DialogError, match="нельзя пропустить"):
        validate_answer(DialogState(), "complaint", [], None, skip=True)


def test_text_not_allowed_where_options_only():
    state = build_state({"complaint": ["pain"]})
    with pytest.raises(DialogError, match="выбрать вариант"):
        validate_answer(state, "location", [], "голова")


@pytest.mark.parametrize(("text", "category"), [
    ("болит горло второй день", "ent"),
    ("высокая температура и озноб", "fever"),
    ("сильный кашель с мокротой", "breathing"),
    ("тошнит и понос", "gi"),
    ("появилась сыпь и зуд", "skin"),
    ("упал и ушиб колено", "trauma"),
    ("кружится голова", "neuro"),
    ("плохо вижу правым глазом", "eyes"),
    ("постоянная тревога и бессонница", "mental"),
    ("ноет поясница", "pain"),
    ("что-то непонятное", "other"),
])
def test_free_text_category_matching(text, category):
    assert text_analysis.match_category(text) == category


def test_pii_is_scrubbed_from_free_text():
    state = DialogState()
    answer = validate_answer(state, "complaint", [], "болит горло, мой тел +7 916 123-45-67, mail a@b.ru, полис 1234567890")
    assert "916" not in answer.text and "@" not in answer.text and "1234567890" not in answer.text
    assert "болит горло" in answer.text


def test_temperature_extraction():
    assert text_analysis.extract_max_temperature("утром 38,2 вечером 39.7") == 39.7
    assert text_analysis.extract_max_temperature("болит голова") is None
