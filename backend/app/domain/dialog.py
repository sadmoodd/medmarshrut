"""Движок диалога: порядок вопросов, валидация ответов, выявление экстренных признаков.

Модуль не зависит от БД и веб-фреймворка: на вход получает ответы, на выход —
следующий вопрос, прогресс или итог. Это упрощает тестирование и перенос
в любой канал (веб, мини-приложение Макс, чат-бот).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import text_analysis
from .knowledge import (
    CATEGORIES,
    CHILD_AGE_GROUPS,
    FERTILE_AGE_GROUPS,
    LOCATIONS,
    QUESTIONS,
    RED_FLAGS,
    STEP_ORDER,
    Question,
    QuestionType,
    RedFlag,
)

MAX_TEXT_LENGTH = 500


class DialogError(ValueError):
    """Некорректный ответ пользователя (понятное сообщение на русском)."""


@dataclass(frozen=True)
class Answer:
    option_ids: tuple[str, ...] = ()
    text: str | None = None
    skipped: bool = False
    prefilled: bool = False  # ответ подставлен из профиля MAX, а не введён пользователем

    def to_dict(self) -> dict:
        return {"option_ids": list(self.option_ids), "text": self.text, "skipped": self.skipped,
                "prefilled": self.prefilled}

    @classmethod
    def from_dict(cls, data: dict) -> "Answer":
        return cls(tuple(data.get("option_ids") or ()), data.get("text"), bool(data.get("skipped")),
                   bool(data.get("prefilled")))


@dataclass
class DialogState:
    """Ответы пользователя в порядке их получения."""

    answers: dict[str, Answer] = field(default_factory=dict)
    profile_available: bool = False  # вход из MAX: есть возраст и пол из профиля

    def option(self, step_id: str) -> str | None:
        answer = self.answers.get(step_id)
        return answer.option_ids[0] if answer and answer.option_ids else None

    def options(self, step_id: str) -> set[str]:
        answer = self.answers.get(step_id)
        return set(answer.option_ids) if answer else set()

    @property
    def category(self) -> str | None:
        answer = self.answers.get("complaint")
        if not answer:
            return None
        if answer.option_ids:
            return answer.option_ids[0]
        return text_analysis.match_category(answer.text or "")

    @property
    def location(self) -> str | None:
        return self.option("location")

    @property
    def age_group(self) -> str | None:
        return self.option("age_group")

    @property
    def is_child(self) -> bool:
        return self.age_group in CHILD_AGE_GROUPS

    def free_texts(self) -> list[str]:
        return [a.text for a in self.answers.values() if a.text]


class Status(str, Enum):
    ACTIVE = "active"
    EMERGENCY = "emergency"
    COMPLETED = "completed"


@dataclass(frozen=True)
class Evaluation:
    status: Status
    question: Question | None
    red_flags: tuple[RedFlag, ...]
    answered: int
    total: int


# --- Условия показа шагов --------------------------------------------------
def _is_applicable(step_id: str, state: DialogState) -> bool:
    """Нужен ли шаг. Пока данных нет — считаем шаг нужным (для честного прогресса)."""
    if step_id == "for_whom":
        return state.profile_available
    if step_id == "pregnancy":
        sex, age = state.option("sex"), state.age_group
        return (sex is None or sex == "female") and (age is None or age in FERTILE_AGE_GROUPS)
    if step_id == "habits":
        return state.age_group not in {"infant", "child"}
    return True


def get_question(step_id: str, state: DialogState) -> Question:
    if step_id == "location":
        category = state.category or "other"
        text, options = LOCATIONS[category]
        return Question(id="location", text=text, qtype=QuestionType.SINGLE, options=options, block="complaint")
    return QUESTIONS[step_id]


def applicable_steps(state: DialogState) -> list[str]:
    return [s for s in STEP_ORDER if _is_applicable(s, state)]


def next_question(state: DialogState) -> Question | None:
    for step_id in applicable_steps(state):
        if step_id not in state.answers:
            return get_question(step_id, state)
    return None


# --- Экстренные признаки ---------------------------------------------------
def detect_red_flags(state: DialogState) -> tuple[RedFlag, ...]:
    """Проверяет ВСЕ накопленные ответы после каждого ввода (непрерывный анализ)."""
    codes: set[str] = set()

    # 1. Варианты ответов, помеченные как экстренные.
    for step_id, answer in state.answers.items():
        question = get_question(step_id, state)
        for option_id in answer.option_ids:
            option = question.option(option_id)
            if option and option.red_flag:
                codes.add(option.red_flag)

    # 2. Комбинации ответов.
    severe = state.option("severity") in {"severe", "unbearable"}
    abdominal = (state.category, state.location) in {("pain", "abdomen"), ("gi", "abdominal_pain")}
    if abdominal and severe:
        codes.add("ACUTE_ABDOMEN")
    if state.is_child and state.category == "fever" and state.location == "t_very_high":
        codes.add("CHILD_HIGH_FEVER")

    # 3. Свободный текст.
    for text in state.free_texts():
        codes |= text_analysis.find_red_flags(text)
        temperature = text_analysis.extract_max_temperature(text)
        if state.is_child and temperature is not None and temperature > 39.5:
            codes.add("CHILD_HIGH_FEVER")

    return tuple(RED_FLAGS[c] for c in RED_FLAGS if c in codes)  # стабильный порядок


def evaluate(state: DialogState) -> Evaluation:
    steps = applicable_steps(state)
    answered = sum(1 for s in steps if s in state.answers)
    flags = detect_red_flags(state)
    if flags:
        return Evaluation(Status.EMERGENCY, None, flags, answered, len(steps))
    question = next_question(state)
    status = Status.ACTIVE if question else Status.COMPLETED
    return Evaluation(status, question, (), answered, len(steps))


# --- Приём ответа ----------------------------------------------------------
def validate_answer(
    state: DialogState,
    step_id: str,
    option_ids: list[str] | tuple[str, ...],
    text: str | None,
    skip: bool = False,
) -> Answer:
    """Проверяет ответ на текущий вопрос и возвращает нормализованный Answer."""
    question = next_question(state)
    if question is None:
        raise DialogError("Опрос уже завершён.")
    if question.id != step_id:
        raise DialogError("Ответ относится не к текущему вопросу. Обновите страницу.")

    text = (text or "").strip() or None
    if text and len(text) > MAX_TEXT_LENGTH:
        raise DialogError(f"Текст слишком длинный: не более {MAX_TEXT_LENGTH} символов.")
    if text and not question.allow_text:
        raise DialogError("Для этого вопроса нужно выбрать вариант ответа.")

    if skip:
        if not question.optional:
            raise DialogError("Этот вопрос нельзя пропустить.")
        return Answer(skipped=True)

    ids = tuple(dict.fromkeys(option_ids))  # без дублей, порядок сохранён
    unknown = [i for i in ids if question.option(i) is None]
    if unknown:
        raise DialogError("Выбран неизвестный вариант ответа.")
    if not ids and not text:
        raise DialogError("Выберите вариант ответа.")
    if question.qtype == QuestionType.SINGLE and len(ids) > 1:
        raise DialogError("Выберите только один вариант.")
    if question.qtype == QuestionType.MULTI and len(ids) > 1:
        if any(question.option(i).exclusive for i in ids):
            raise DialogError("Вариант «Нет» нельзя совмещать с другими.")

    if text:
        text = text_analysis.scrub_pii(text)
    return Answer(option_ids=ids, text=text)


def answer_label(step_id: str, answer: Answer, state: DialogState) -> str:
    """Человекочитаемый ответ для истории диалога."""
    if answer.skipped:
        return "Пропущено"
    question = get_question(step_id, state)
    parts = [question.option(i).label for i in answer.option_ids if question.option(i)]
    if answer.text:
        if step_id == "complaint" and not answer.option_ids:
            category = text_analysis.match_category(answer.text)
            return f"«{answer.text}» (тема: {CATEGORIES[category]})"
        parts.append(f"«{answer.text}»")
    label = "; ".join(parts)
    return f"{label} (из профиля MAX)" if answer.prefilled else label
