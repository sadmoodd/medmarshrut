"""Формирование рекомендации: специалист, срочность, место обращения, обоснование.

Правила прозрачные (rule-based), каждое сработавшее правило добавляет строку
в обоснование. Модуль НЕ ставит диагноз и НЕ называет лекарств и дозировок.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .dialog import DialogState, get_question
from .knowledge import CATEGORIES, LOCATIONS, RedFlag


class Urgency(str, Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    PLANNED = "planned"
    SELF_CARE = "self_care"


class CarePlace(str, Enum):
    AMBULANCE = "ambulance"
    ER = "er"
    CLINIC = "clinic"
    TELEMEDICINE = "telemedicine"
    PHARMACY = "pharmacy"


URGENCY_LABELS = {
    Urgency.EMERGENCY: "Экстренно — помощь нужна немедленно",
    Urgency.URGENT: "Срочно — в течение 24 часов",
    Urgency.PLANNED: "Планово — запишитесь на приём",
    Urgency.SELF_CARE: "Самопомощь и наблюдение",
}

CARE_PLACE_LABELS = {
    CarePlace.AMBULANCE: "Скорая помощь: 103 или 112",
    CarePlace.ER: "Приёмный покой или травмпункт",
    CarePlace.CLINIC: "Поликлиника",
    CarePlace.TELEMEDICINE: "Телемедицинская консультация",
    CarePlace.PHARMACY: "Аптека: консультация фармацевта",
}

ENT = "Оториноларинголог (ЛОР)"
SPECIALTY_DEFAULT = {
    "pain": "Терапевт",
    "fever": "Терапевт",
    "breathing": "Терапевт",
    "gi": "Гастроэнтеролог",
    "skin": "Дерматолог",
    "neuro": "Невролог",
    "trauma": "Травматолог",
    "ent": ENT,
    "eyes": "Офтальмолог",
    "mental": "Психиатр или психотерапевт",
    "other": "Терапевт",
}
SPECIALTY_BY_LOCATION = {
    ("pain", "head"): "Невролог",
    ("pain", "chest"): "Кардиолог",
    ("pain", "abdomen"): "Гастроэнтеролог",
    ("pain", "back"): "Невролог",
    ("pain", "throat"): ENT,
    ("pain", "ear"): ENT,
    ("pain", "teeth"): "Стоматолог",
    ("breathing", "runny_nose"): ENT,
    ("skin", "wound"): "Хирург",
    ("skin", "burn"): "Хирург",
    ("trauma", "cut"): "Хирург",
    ("trauma", "burn"): "Хирург",
    ("neuro", "headache"): "Невролог",
    ("other", "urination"): "Уролог",
}

# Сочетания, при которых допустима самопомощь (если нет факторов риска).
SELF_CARE_ELIGIBLE = {
    ("fever", "t_low"), ("fever", "t_mid"),
    ("breathing", "cough"), ("breathing", "runny_nose"),
    ("gi", "heartburn"), ("gi", "diarrhea"), ("gi", "constipation"), ("gi", "nausea"),
    ("skin", "itch"),
    ("ent", "nose"), ("ent", "throat"),
    ("eyes", "red_eye"),
    ("mental", "sleep"),
    ("other", "weakness"),
}
TELEMEDICINE_SUITABLE = {"fever", "breathing", "gi", "skin", "mental", "other", "ent"}
ER_URGENT_CATEGORIES = {"trauma"}

SELF_CARE_ADVICE = (
    "Больше отдыхайте, пейте достаточно жидкости и следите за самочувствием.",
    "Любые лекарства подбирайте только после консультации с врачом или фармацевтом.",
    "Если через 2–3 дня не станет лучше или появятся новые симптомы — запишитесь к врачу.",
)


@dataclass
class Recommendation:
    specialty: str
    urgency: Urgency
    care_place: CarePlace
    rationale: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    alternatives: list[CarePlace] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "specialty": self.specialty,
            "urgency": self.urgency.value,
            "care_place": self.care_place.value,
            "rationale": self.rationale,
            "advice": self.advice,
            "alternatives": [a.value for a in self.alternatives],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recommendation":
        return cls(
            specialty=data["specialty"],
            urgency=Urgency(data["urgency"]),
            care_place=CarePlace(data["care_place"]),
            rationale=list(data.get("rationale", [])),
            advice=list(data.get("advice", [])),
            alternatives=[CarePlace(a) for a in data.get("alternatives", [])],
        )


def build_emergency(flags: tuple[RedFlag, ...]) -> Recommendation:
    return Recommendation(
        specialty="Бригада скорой медицинской помощи",
        urgency=Urgency.EMERGENCY,
        care_place=CarePlace.AMBULANCE,
        rationale=[f"Выявлен экстренный признак: {f.title.lower()}" for f in flags],
        advice=["Не дожидайтесь окончания опроса — позвоните 103 или 112 прямо сейчас."],
    )


def _label(step_id: str, state: DialogState) -> str:
    answer = state.answers.get(step_id)
    if not answer or not answer.option_ids:
        return ""
    question = get_question(step_id, state)
    return ", ".join(question.option(i).label for i in answer.option_ids if question.option(i)).lower()


def _specialty(state: DialogState, rationale: list[str]) -> str:
    category = state.category or "other"
    specialty = SPECIALTY_BY_LOCATION.get((category, state.location), SPECIALTY_DEFAULT[category])
    if state.is_child and specialty == "Терапевт":
        rationale.append("Пациент — ребёнок, поэтому первичный приём проводит педиатр")
        return "Педиатр"
    if state.is_child:
        rationale.append("Пациент — ребёнок: обратитесь к детскому специалисту или к педиатру")
    return specialty


def _urgent_reasons(state: DialogState) -> list[str]:
    reasons: list[str] = []
    category, location = state.category, state.location
    severity, duration = state.option("severity"), state.option("duration")
    pregnant = state.option("pregnancy") == "pregnant"
    chronic = state.options("chronic")

    if severity in {"severe", "unbearable"}:
        reasons.append("Симптомы выражены сильно")
    if category == "fever":
        if location == "t_very_high":
            reasons.append("Температура выше 39,5 °C")
        if location == "t_high" and duration in {"d4_7", "gt7", "gt30"}:
            reasons.append("Температура выше 38,5 °C держится больше 3 дней")
        if state.age_group == "infant" and location != "t_low":
            reasons.append("Повышенная температура у ребёнка до года")
        if location in {"t_high", "t_very_high"} and chronic & {"diabetes", "oncology", "heart"}:
            reasons.append("Высокая температура на фоне хронического заболевания")
    if category == "trauma":
        reasons.append("После травмы нужен очный осмотр, чтобы исключить повреждения")
    if (category, location) in {("eyes", "vision_loss"), ("eyes", "eye_injury")}:
        reasons.append("Внезапные нарушения зрения и травмы глаза требуют осмотра в день обращения")
    if (category, location) in {("skin", "burn"), ("breathing", "dyspnea_exertion")}:
        reasons.append("Такой симптом требует осмотра врача в ближайшие часы")
    if pregnant and category in {"pain", "gi", "fever"}:
        reasons.append("Во время беременности такие симптомы нужно показать врачу без промедления")
    if state.age_group == "senior" and category in {"fever", "breathing"} and severity != "mild":
        reasons.append("В возрасте 65+ инфекции чаще протекают тяжелее")
    return reasons


def _has_risk_factors(state: DialogState) -> bool:
    return bool(
        state.age_group in {"infant", "senior"}
        or state.option("pregnancy") in {"pregnant", "lactation"}
        or (state.options("chronic") - {"none"})
    )


def _preparation_advice(state: DialogState) -> list[str]:
    advice: list[str] = []
    chronic = state.options("chronic") - {"none"}
    if chronic:
        advice.append(f"Сообщите врачу о хронических заболеваниях: {_label('chronic', state)}.")
    if state.option("medications") in {"regular", "situational"}:
        advice.append("Возьмите с собой список лекарств, которые вы принимаете.")
    if "drug" in state.options("allergies"):
        advice.append("Обязательно предупредите врача о лекарственной аллергии.")
    if state.option("pregnancy") in {"pregnant", "lactation"}:
        advice.append("Сообщите врачу о беременности или грудном вскармливании.")
    if state.option("surgeries") in {"surgery", "hospital"}:
        advice.append("Возьмите выписки об операциях и госпитализациях за последний год.")
    return advice


def build_recommendation(state: DialogState) -> Recommendation:
    """Рекомендация для завершённого опроса без экстренных признаков."""
    category = state.category or "other"
    rationale = [f"Основная жалоба: {CATEGORIES[category].lower()}"]
    if state.location:
        rationale.append(f"Уточнение: {_label('location', state)}")
    if state.option("duration"):
        rationale.append(f"Длительность: {_label('duration', state)}")
    if state.option("severity"):
        rationale.append(f"Выраженность: {_label('severity', state)}")

    specialty = _specialty(state, rationale)
    urgent = _urgent_reasons(state)

    if urgent:
        rationale.extend(urgent)
        place = CarePlace.ER if (
            category in ER_URGENT_CATEGORIES
            or (category, state.location) in {("eyes", "eye_injury"), ("eyes", "vision_loss"), ("skin", "burn")}
        ) else CarePlace.CLINIC
        advice = ["Обратитесь к врачу сегодня. Если станет хуже — вызывайте скорую помощь: 103 или 112."]
        return Recommendation(specialty, Urgency.URGENT, place, rationale,
                              advice + _preparation_advice(state))

    eligible = (category, state.location) in SELF_CARE_ELIGIBLE
    mild_and_recent = state.option("severity") == "mild" and state.option("duration") in {"lt1d", "d1_3"}
    if eligible and mild_and_recent and not _has_risk_factors(state):
        rationale.append("Симптомы слабо выражены, появились недавно, факторов риска нет")
        return Recommendation(specialty, Urgency.SELF_CARE, CarePlace.PHARMACY, rationale,
                              list(SELF_CARE_ADVICE), [CarePlace.TELEMEDICINE])

    if state.option("duration") == "gt30":
        rationale.append("Симптомы длятся больше месяца: нужен плановый осмотр")
    else:
        rationale.append("Экстренная помощь не требуется, но нужен осмотр врача")
    if _has_risk_factors(state):
        rationale.append("Есть факторы риска (возраст, беременность или хронические заболевания)")
    alternatives = [CarePlace.TELEMEDICINE] if category in TELEMEDICINE_SUITABLE else []
    advice = ["Запишитесь на приём в поликлинику в ближайшие дни."] + _preparation_advice(state)
    return Recommendation(specialty, Urgency.PLANNED, CarePlace.CLINIC, rationale, advice, alternatives)


__all__ = [
    "CARE_PLACE_LABELS", "URGENCY_LABELS", "CarePlace", "Recommendation", "Urgency",
    "build_emergency", "build_recommendation", "LOCATIONS",
]
