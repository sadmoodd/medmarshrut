"""ORM-модели. Персональные данные (ФИО, телефон, адрес, точный возраст) не хранятся.

Медицинские ответы и рекомендация шифруются на уровне приложения (EncryptedJSON).
Сессии удаляются автоматически после истечения expires_at.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .security import EncryptedJSON


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PatientSession(Base):
    __tablename__ = "patient_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active','emergency','completed')", name="ck_session_status"),
        CheckConstraint("channel IN ('web','max')", name="ck_session_channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(8), default="web")
    external_user_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # Только возрастная группа и пол из профиля MAX (зашифровано). СНИЛС, ФИО, телефон не хранятся.
    profile: Mapped[dict | None] = mapped_column(EncryptedJSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    kb_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    answers: Mapped[list["SessionAnswer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionAnswer.seq"
    )
    result: Mapped["TriageResult | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    emergency_events: Mapped[list["EmergencyEvent"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionAnswer(Base):
    __tablename__ = "session_answers"
    __table_args__ = (UniqueConstraint("session_id", "step_id", name="uq_answer_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_sessions.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    step_id: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(EncryptedJSON)  # {option_ids, text, skipped}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[PatientSession] = relationship(back_populates="answers")


class TriageResult(Base):
    __tablename__ = "triage_results"
    __table_args__ = (
        CheckConstraint("urgency IN ('emergency','urgent','planned','self_care')", name="ck_result_urgency"),
        CheckConstraint(
            "care_place IN ('ambulance','er','clinic','telemedicine','pharmacy')", name="ck_result_place"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patient_sessions.id", ondelete="CASCADE"), unique=True
    )
    urgency: Mapped[str] = mapped_column(String(16), index=True)
    care_place: Mapped[str] = mapped_column(String(16))
    specialty: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(EncryptedJSON)  # полная рекомендация с обоснованием
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[PatientSession] = relationship(back_populates="result")


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patient_sessions.id", ondelete="CASCADE"), index=True)
    red_flag_code: Mapped[str] = mapped_column(String(32), index=True)
    step_id: Mapped[str] = mapped_column(String(32))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[PatientSession] = relationship(back_populates="emergency_events")
