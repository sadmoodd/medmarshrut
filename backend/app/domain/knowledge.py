"""База знаний опросника: категории жалоб, вопросы, варианты ответов.

Знания хранятся в коде (а не в БД), чтобы они были версионируемыми,
проходили ревью вместе с кодом и покрывались тестами.
Медицинская логика согласуется аналитиком предметной области.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

KB_VERSION = "2026.11-mvp1"


class QuestionType(str, Enum):
    SINGLE = "single"
    MULTI = "multi"


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    red_flag: str | None = None  # код критического признака, если вариант экстренный
    exclusive: bool = False  # «Нет / ничего из перечисленного» нельзя совмещать с другими


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    qtype: QuestionType
    options: tuple[Option, ...]
    block: str  # complaint | profile | anamnesis
    hint: str | None = None
    allow_text: bool = False
    optional: bool = False
    text_placeholder: str | None = None

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


def _opts(*items: tuple) -> tuple[Option, ...]:
    return tuple(Option(*item) for item in items)


# --- Категории основной жалобы ---------------------------------------------
CATEGORIES: dict[str, str] = {
    "pain": "Боль",
    "fever": "Температура",
    "breathing": "Дыхание, кашель",
    "gi": "Желудок и кишечник (ЖКТ)",
    "skin": "Кожа",
    "neuro": "Голова, головокружение, онемение",
    "trauma": "Травма",
    "ent": "Ухо, горло, нос",
    "eyes": "Глаза",
    "mental": "Настроение, тревога, сон",
    "other": "Другое",
}

# --- Уточнение (локализация) для каждой категории --------------------------
LOCATIONS: dict[str, tuple[str, tuple[Option, ...]]] = {
    "pain": ("Где именно болит?", _opts(
        ("head", "Голова"),
        ("chest", "Грудная клетка", "CHEST_PAIN"),
        ("abdomen", "Живот"),
        ("back", "Спина или поясница"),
        ("joints", "Суставы или мышцы"),
        ("throat", "Горло"),
        ("ear", "Ухо"),
        ("teeth", "Зубы"),
        ("other", "Другое место"),
    )),
    "fever": ("Какая температура сейчас?", _opts(
        ("t_low", "До 37,5 °C"),
        ("t_mid", "37,5–38,5 °C"),
        ("t_high", "38,5–39,5 °C"),
        ("t_very_high", "Выше 39,5 °C"),
        ("t_unknown", "Не измерял(а), но ощущаю жар"),
    )),
    "breathing": ("Что именно беспокоит?", _opts(
        ("cough", "Кашель"),
        ("runny_nose", "Насморк, заложенность носа"),
        ("dyspnea_exertion", "Одышка при физической нагрузке"),
        ("dyspnea_rest", "Нехватка воздуха в покое", "DYSPNEA_REST"),
    )),
    "gi": ("Что именно беспокоит?", _opts(
        ("nausea", "Тошнота или рвота"),
        ("diarrhea", "Жидкий стул"),
        ("constipation", "Запор"),
        ("heartburn", "Изжога, отрыжка"),
        ("abdominal_pain", "Боль в животе"),
        ("gi_blood", "Кровь в рвоте или стуле, чёрный стул", "BLEEDING"),
    )),
    "skin": ("Что происходит с кожей?", _opts(
        ("rash", "Сыпь"),
        ("itch", "Зуд"),
        ("mole", "Изменилась родинка или пятно"),
        ("wound", "Рана или ссадина"),
        ("burn", "Ожог"),
        ("face_swelling", "Внезапный отёк лица, губ или языка", "ANAPHYLAXIS"),
    )),
    "neuro": ("Что именно беспокоит?", _opts(
        ("headache", "Головная боль"),
        ("dizziness", "Головокружение"),
        ("tingling", "Онемение или покалывание пальцев"),
        ("stroke_signs", "Внезапная слабость половины тела, перекос лица или нарушение речи", "STROKE"),
        ("seizure", "Судороги", "SEIZURES"),
        ("fainting", "Обморок, потеря сознания", "LOSS_OF_CONSCIOUSNESS"),
    )),
    "trauma": ("Что травмировано?", _opts(
        ("head_loc", "Голова, была потеря сознания", "HEAD_TRAUMA_LOC"),
        ("head", "Голова, сознание не терял(а)"),
        ("limb", "Рука или нога: ушиб, вывих, возможный перелом"),
        ("spine", "Спина или шея"),
        ("cut", "Порез или глубокая рана"),
        ("burn", "Ожог"),
    )),
    "ent": ("Что именно беспокоит?", _opts(
        ("ear", "Ухо: боль, заложенность, снижение слуха"),
        ("throat", "Горло: боль при глотании"),
        ("nose", "Нос: заложенность, выделения"),
        ("nosebleed", "Носовое кровотечение"),
    )),
    "eyes": ("Что происходит с глазами?", _opts(
        ("red_eye", "Покраснение, слезотечение, зуд"),
        ("vision_loss", "Внезапное снижение или потеря зрения"),
        ("eye_injury", "Травма или попадание инородного тела"),
        ("vision_gradual", "Постепенное ухудшение зрения"),
    )),
    "mental": ("Что вас беспокоит?", _opts(
        ("anxiety", "Тревога, панические атаки"),
        ("low_mood", "Подавленное настроение"),
        ("sleep", "Нарушения сна"),
        ("self_harm", "Мысли о причинении вреда себе", "SUICIDAL"),
    )),
    "other": ("Уточните, пожалуйста:", _opts(
        ("weakness", "Общая слабость, быстрая утомляемость"),
        ("pressure", "Повышенное артериальное давление"),
        ("urination", "Проблемы с мочеиспусканием"),
        ("other", "Другое"),
    )),
}

CHILD_AGE_GROUPS = frozenset({"infant", "child", "teen"})
FERTILE_AGE_GROUPS = frozenset({"teen", "adult"})

# --- Статические вопросы ---------------------------------------------------
QUESTIONS: dict[str, Question] = {
    # Задаётся только при входе из MAX: профиль описывает владельца аккаунта,
    # а помощь может быть нужна ребёнку или родственнику.
    "for_whom": Question(
        id="for_whom",
        text="Для кого вы ищете помощь?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("self", "Для себя"),
            ("other", "Для другого человека: ребёнка или родственника"),
        ),
        block="profile",
        hint="Если для себя — возраст и пол возьмём из вашего профиля MAX.",
    ),
    "complaint": Question(
        id="complaint",
        text="Что беспокоит вас больше всего? Выберите вариант или опишите своими словами.",
        qtype=QuestionType.SINGLE,
        options=_opts(*CATEGORIES.items()),
        block="complaint",
        allow_text=True,
        text_placeholder="Например: болит горло второй день",
    ),
    "danger_signs": Question(
        id="danger_signs",
        text="Есть ли у вас сейчас что-то из этого списка? Это важно для вашей безопасности.",
        qtype=QuestionType.MULTI,
        options=_opts(
            ("chest", "Боль, давление или жжение в груди", "CHEST_PAIN"),
            ("dyspnea", "Сильная нехватка воздуха в покое", "DYSPNEA_REST"),
            ("faint", "Потеря сознания или обморок", "LOSS_OF_CONSCIOUSNESS"),
            ("seizure", "Судороги", "SEIZURES"),
            ("bleeding", "Кровотечение, которое не останавливается", "BLEEDING"),
            ("fast", "Перекос лица, слабость в руке, нарушение речи", "STROKE"),
            ("anaphylaxis", "Отёк лица или горла, трудно дышать после укуса, лекарства или еды", "ANAPHYLAXIS"),
            ("abdomen", "Внезапная сильная боль в животе", "ACUTE_ABDOMEN"),
            ("none", "Ничего из перечисленного", None, True),
        ),
        block="complaint",
        hint="Можно выбрать несколько вариантов.",
        allow_text=True,
        text_placeholder="Другие симптомы (необязательно)",
    ),
    "age_group": Question(
        id="age_group",
        text="Сколько лет человеку, для которого вы ищете помощь?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("infant", "До 1 года"),
            ("child", "1–13 лет"),
            ("teen", "14–17 лет"),
            ("adult", "18–49 лет"),
            ("middle", "50–64 года"),
            ("senior", "65 лет и старше"),
        ),
        block="profile",
        hint="Точный возраст не нужен: достаточно возрастной группы.",
    ),
    "sex": Question(
        id="sex",
        text="Укажите пол.",
        qtype=QuestionType.SINGLE,
        options=_opts(("male", "Мужской"), ("female", "Женский")),
        block="profile",
    ),
    "duration": Question(
        id="duration",
        text="Как давно это началось?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("lt1d", "Меньше суток"),
            ("d1_3", "1–3 дня"),
            ("d4_7", "4–7 дней"),
            ("gt7", "Больше недели"),
            ("gt30", "Больше месяца"),
        ),
        block="complaint",
    ),
    "severity": Question(
        id="severity",
        text="Насколько сильно это вас беспокоит?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("mild", "Слабо, обычным делам не мешает"),
            ("moderate", "Умеренно, мешает, но терпимо"),
            ("severe", "Сильно, трудно заниматься делами"),
            ("unbearable", "Невыносимо"),
        ),
        block="complaint",
    ),
    "chronic": Question(
        id="chronic",
        text="Есть ли хронические заболевания?",
        qtype=QuestionType.MULTI,
        options=_opts(
            ("none", "Нет", None, True),
            ("diabetes", "Сахарный диабет"),
            ("hypertension", "Гипертония"),
            ("asthma", "Бронхиальная астма или ХОБЛ"),
            ("heart", "Болезни сердца"),
            ("oncology", "Онкологическое заболевание"),
            ("kidney", "Болезни почек"),
            ("other", "Другое"),
        ),
        block="anamnesis",
        hint="Можно выбрать несколько вариантов.",
    ),
    "medications": Question(
        id="medications",
        text="Принимаете ли вы лекарства?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("none", "Не принимаю"),
            ("regular", "Принимаю постоянно"),
            ("situational", "Принимаю время от времени"),
        ),
        block="anamnesis",
        hint="Названия лекарств здесь указывать не нужно: сообщите их врачу на приёме.",
    ),
    "allergies": Question(
        id="allergies",
        text="Есть ли аллергия?",
        qtype=QuestionType.MULTI,
        options=_opts(
            ("none", "Нет", None, True),
            ("drug", "На лекарства"),
            ("food", "На продукты"),
            ("other", "Другая (пыльца, укусы насекомых и т. п.)"),
            ("unknown", "Не знаю", None, True),
        ),
        block="anamnesis",
    ),
    "surgeries": Question(
        id="surgeries",
        text="Были ли операции или госпитализации за последний год?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("no", "Нет"),
            ("surgery", "Да, была операция"),
            ("hospital", "Да, была госпитализация без операции"),
        ),
        block="anamnesis",
    ),
    "heredity": Question(
        id="heredity",
        text="Есть ли у близких родственников эти заболевания?",
        qtype=QuestionType.MULTI,
        options=_opts(
            ("none", "Нет", None, True),
            ("cvd", "Болезни сердца и сосудов"),
            ("oncology", "Онкологические заболевания"),
            ("diabetes", "Сахарный диабет"),
            ("unknown", "Не знаю", None, True),
        ),
        block="anamnesis",
    ),
    "pregnancy": Question(
        id="pregnancy",
        text="Есть ли сейчас беременность или грудное вскармливание?",
        qtype=QuestionType.SINGLE,
        options=_opts(
            ("no", "Нет"),
            ("pregnant", "Беременность"),
            ("lactation", "Грудное вскармливание"),
            ("unknown", "Не уверена"),
        ),
        block="anamnesis",
    ),
    "habits": Question(
        id="habits",
        text="Есть ли вредные привычки? Этот вопрос можно пропустить.",
        qtype=QuestionType.MULTI,
        options=_opts(
            ("none", "Нет", None, True),
            ("smoking", "Курение"),
            ("alcohol", "Регулярное употребление алкоголя"),
        ),
        block="anamnesis",
        optional=True,
    ),
}

# Порядок шагов диалога. Жалоба и экстренные признаки идут первыми,
# чтобы критическое состояние выявлялось как можно раньше.
STEP_ORDER: tuple[str, ...] = (
    "for_whom",
    "complaint",
    "location",
    "danger_signs",
    "age_group",
    "sex",
    "duration",
    "severity",
    "chronic",
    "medications",
    "allergies",
    "surgeries",
    "heredity",
    "pregnancy",
    "habits",
)


@dataclass(frozen=True)
class RedFlag:
    code: str
    title: str
    explanation: str


RED_FLAGS: dict[str, RedFlag] = {f.code: f for f in (
    RedFlag("CHEST_PAIN", "Боль в груди",
            "Боль, давление или жжение в груди могут быть признаком сердечного приступа. Важна каждая минута."),
    RedFlag("DYSPNEA_REST", "Одышка в покое",
            "Нехватка воздуха в покое требует срочного осмотра бригадой скорой помощи."),
    RedFlag("LOSS_OF_CONSCIOUSNESS", "Потеря сознания",
            "Потеря сознания может быть признаком серьёзного нарушения работы сердца или мозга."),
    RedFlag("SEIZURES", "Судороги",
            "Судороги требуют немедленной медицинской помощи. Не оставляйте человека одного."),
    RedFlag("BLEEDING", "Кровотечение",
            "Сильное или внутреннее кровотечение опасно для жизни и требует экстренной помощи."),
    RedFlag("STROKE", "Признаки инсульта (FAST)",
            "Перекос лица, слабость в руке и нарушение речи — признаки инсульта. "
            "Запомните время начала симптомов и сообщите его бригаде."),
    RedFlag("ANAPHYLAXIS", "Признаки тяжёлой аллергической реакции",
            "Отёк лица или горла и затруднённое дыхание могут быстро нарастать и угрожать жизни."),
    RedFlag("ACUTE_ABDOMEN", "Острая боль в животе",
            "Внезапная сильная боль в животе может требовать срочной операции."),
    RedFlag("CHILD_HIGH_FEVER", "Температура выше 39,5 °C у ребёнка",
            "Очень высокая температура у ребёнка требует немедленного осмотра врачом."),
    RedFlag("HEAD_TRAUMA_LOC", "Травма головы с потерей сознания",
            "После травмы головы с потерей сознания возможны опасные внутричерепные повреждения."),
    RedFlag("SUICIDAL", "Мысли о причинении вреда себе",
            "Вы не одни, и помощь доступна прямо сейчас. Позвоните 112 и, если можете, "
            "попросите близкого человека побыть рядом."),
)}

DISCLAIMER_START = (
    "Бот не ставит диагноз и не заменяет врача. Он помогает понять, к какому специалисту "
    "и насколько срочно стоит обратиться."
)
DISCLAIMER_END = "При ухудшении состояния вызывайте скорую помощь: 103 или 112."
EMERGENCY_MESSAGE = "Вызовите скорую помощь: 103 или 112."
EMERGENCY_ADVICE = (
    "Не дожидайтесь окончания опроса — позвоните прямо сейчас.",
    "Сообщите диспетчеру симптомы и точный адрес.",
    "По возможности попросите кого-то побыть рядом и открыть дверь бригаде.",
)
