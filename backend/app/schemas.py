"""Pydantic-схемы публичного API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .domain.dialog import MAX_TEXT_LENGTH


class SessionCreateIn(BaseModel):
    channel: Literal["web", "max"] = "web"


class AnswerIn(BaseModel):
    step_id: str = Field(max_length=32)
    option_ids: list[str] = Field(default_factory=list, max_length=20)
    text: str | None = Field(default=None, max_length=MAX_TEXT_LENGTH)
    skip: bool = False


class OptionOut(BaseModel):
    id: str
    label: str
    exclusive: bool


class QuestionOut(BaseModel):
    id: str
    text: str
    type: Literal["single", "multi"]
    block: str
    hint: str | None
    options: list[OptionOut]
    allow_text: bool
    text_placeholder: str | None
    optional: bool


class ProgressOut(BaseModel):
    answered: int
    total: int
    percent: int


class HistoryItem(BaseModel):
    step_id: str
    question: str
    answer: str


class RedFlagOut(BaseModel):
    code: str
    title: str
    explanation: str


class EmergencyOut(BaseModel):
    message: str
    flags: list[RedFlagOut]
    advice: list[str]


class RecommendationOut(BaseModel):
    specialty: str
    urgency: str
    urgency_label: str
    care_place: str
    care_place_label: str
    alternatives: list[str]
    rationale: list[str]
    advice: list[str]


class SessionView(BaseModel):
    session_id: uuid.UUID
    status: Literal["active", "emergency", "completed"]
    question: QuestionOut | None
    progress: ProgressOut
    history: list[HistoryItem]
    can_go_back: bool
    emergency: EmergencyOut | None
    recommendation: RecommendationOut | None
    disclaimer_start: str
    disclaimer_end: str
    expires_at: datetime


class SessionCreatedOut(SessionView):
    session_token: str = Field(description="Секрет сессии. Передавайте в заголовке X-Session-Token.")
    greeting_name: str | None = Field(default=None, description="Имя для приветствия (не сохраняется)")


class MaxAuthIn(BaseModel):
    token: str = Field(min_length=10, max_length=4096, description="JWT из query-параметра token")
