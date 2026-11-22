"""Анализ свободного текста на основе ключевых слов (keyword-matching).

Используются основы слов и регулярные выражения, поэтому распознаются разные
словоформы («болит», «боль», «боли»). Отрицания намеренно не учитываются:
для экстренных признаков ложная тревога безопаснее пропуска (принцип over-triage).
"""
from __future__ import annotations

import re

_PUNCT_RE = re.compile(r"[^\w\s.,]+", re.UNICODE)
_SPACES_RE = re.compile(r"\s+")

# Порядок важен: при равном числе совпадений побеждает категория выше в списке.
CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "trauma": (r"травм", r"ушиб", r"упал", r"перелом", r"вывих", r"порез", r"ожог", r"обжег", r"удар"),
    "neuro": (r"головокруж", r"кружится", r"онемен", r"онемел", r"мигрен", r"покалыва", r"судорог"),
    "breathing": (r"кашл", r"одышк", r"насморк", r"дыш", r"мокрот", r"задыха", r"сопл"),
    "fever": (r"температур", r"\bжар", r"лихорад", r"озноб", r"знобит"),
    "gi": (r"тошн", r"рвот", r"рвет", r"понос", r"диаре", r"запор", r"изжог", r"живот", r"желуд", r"стул"),
    "skin": (r"сып", r"\bзуд", r"чешет", r"чешу", r"пятн", r"родинк", r"кож", r"прыщ", r"крапивниц"),
    "ent": (r"\bух[оау]", r"\bуш[иа]", r"горл", r"\bнос", r"слух", r"ангин", r"глота"),
    "eyes": (r"глаз", r"зрени", r"\bвижу"),
    "mental": (r"тревог", r"паник", r"депресс", r"настроени", r"бессонниц", r"уснуть", r"\bсон\b", r"стресс",
               r"не хочу жить", r"суицид"),
    "pain": (r"\bбол", r"\bноет", r"ломит", r"давит", r"колет", r"груд", r"сердц"),
}

RED_FLAG_PATTERNS: dict[str, tuple[str, ...]] = {
    "CHEST_PAIN": (
        r"(бол|давит|давлен|жжет|жжени|сдавл|колет)\w*\s+(\w+\s+)?(в\s+|за\s+)?(груд|сердц)",
        r"(груд|грудин|сердц)\w*\s+(\w+\s+)?(бол|давит|жжет|сдавл|колет)",
    ),
    "DYSPNEA_REST": (
        r"задыха", r"не\s+могу\s+дышать", r"нечем\s+дышать", r"удушь", r"не\s+хватает\s+воздуха",
        r"нехватк\w*\s+воздуха",
    ),
    "LOSS_OF_CONSCIOUSNESS": (r"потер\w*\s+сознани", r"без\s+сознани", r"обморок", r"отключил\w*"),
    "SEIZURES": (r"судорог", r"припад", r"эпилептич"),
    "BLEEDING": (
        r"кровотечени", r"кровь\s+не\s+останавлива", r"(рвота|рвет|рвало|стошнило)\s+кровью",
        r"кровав\w*\s+рвот", r"черн\w*\s+стул", r"кровь\s+в\s+(стуле|рвоте|моче)",
    ),
    "STROKE": (
        r"перекос", r"онемел\w*\s+(половин|пол\s+лица|лиц)", r"не\s+могу\s+говорить", r"нарушен\w*\s+реч",
        r"речь\s+нарушен", r"невнятн\w*\s+реч", r"инсульт", r"асимметри\w*\s+лиц", r"отнял\w*\s+(рук|ног)",
    ),
    "ANAPHYLAXIS": (
        r"отек\w*\s+(горла|лица|губ|языка|гортани)", r"(отекл|опух)\w*\s+(\w+\s+)?(горло|лицо|губ|язык)",
        r"анафилак", r"квинке",
    ),
    "ACUTE_ABDOMEN": (
        r"(резк|остр|сильн|кинжальн|невыносим|адск)\w*\s+(\w+\s+)?бол\w*\s+(\w+\s+)?живот",
        r"живот\w*\s+(как\s+)?доск",
    ),
    "HEAD_TRAUMA_LOC": (r"(удар|травм|ушиб)\w*\s+(\w+\s+)?голов\w*.*сознани",),
    "SUICIDAL": (
        r"покончить\s+с\s+собой", r"суицид", r"не\s+хочу\s+жить", r"убить\s+себя",
        r"причинить\s+себе\s+вред", r"свести\s+счет\w*\s+с\s+жизнью",
    ),
}

_COMPILED_CATEGORY = {k: tuple(re.compile(p) for p in v) for k, v in CATEGORY_PATTERNS.items()}
_COMPILED_RED = {k: tuple(re.compile(p) for p in v) for k, v in RED_FLAG_PATTERNS.items()}
_TEMP_RE = re.compile(r"(?<!\d)(3[5-9]|4[0-2])(?:[.,](\d))?(?!\d)")

_PHONE_RE = re.compile(r"(?:\+7|\b8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")  # СНИЛС, полис ОМС, паспорт


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = _PUNCT_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def match_category(text: str) -> str:
    """Определяет категорию жалобы по свободному тексту. По умолчанию — «other»."""
    norm = normalize(text)
    best, best_score = "other", 0
    for category, patterns in _COMPILED_CATEGORY.items():
        score = sum(1 for p in patterns if p.search(norm))
        if score > best_score:
            best, best_score = category, score
    return best


def find_red_flags(text: str) -> set[str]:
    norm = normalize(text)
    return {code for code, patterns in _COMPILED_RED.items() if any(p.search(norm) for p in patterns)}


def extract_max_temperature(text: str) -> float | None:
    """Ищет в тексте значения температуры (35–42 °C) и возвращает максимальное."""
    values = []
    for whole, frac in _TEMP_RE.findall(text):
        values.append(float(f"{whole}.{frac or 0}"))
    return max(values) if values else None


def scrub_pii(text: str) -> str:
    """Удаляет из свободного текста телефоны, e-mail и длинные номера документов.

    Принцип минимизации ПДн (ФЗ-152): для маршрутизации эти данные не нужны.
    """
    text = _EMAIL_RE.sub("[скрыто]", text)
    text = _PHONE_RE.sub("[скрыто]", text)
    return _LONG_NUMBER_RE.sub("[скрыто]", text)
