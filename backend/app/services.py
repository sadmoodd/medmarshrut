"""Прикладной слой: связывает движок диалога с хранилищем."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import schemas
from .config import get_settings
from .domain import dialog, triage
from .domain.knowledge import (
    DISCLAIMER_END,
    DISCLAIMER_START,
    EMERGENCY_ADVICE,
    EMERGENCY_MESSAGE,
    KB_VERSION,
)
from .models import EmergencyEvent, PatientSession, SessionAnswer, TriageResult, utcnow
from .security import hash_token, new_session_token, pseudonymize, token_matches


PROFILE_STEPS = ("age_group", "sex")


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class Conflict(Exception):
    pass


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class SessionService:
    def __init__(self, db: Session):
        self.db = db
        self.ttl = timedelta(hours=get_settings().session_ttl_hours)

    # --- жизненный цикл ----------------------------------------------------
    def create(
        self,
        channel: str = "web",
        external_user_id: str | None = None,
        profile: dict | None = None,
    ) -> tuple[PatientSession, str]:
        token = new_session_token()
        profile = {k: v for k, v in (profile or {}).items() if k in PROFILE_STEPS and v} or None
        session = PatientSession(
            token_hash=hash_token(token),
            channel=channel,
            external_user_hash=pseudonymize(external_user_id) if external_user_id else None,
            profile=profile,
            status=dialog.Status.ACTIVE.value,
            kb_version=KB_VERSION,
            expires_at=utcnow() + self.ttl,
        )
        self.db.add(session)
        self.db.commit()
        return session, token

    def get_authorized(self, session_id: uuid.UUID, token: str | None) -> PatientSession:
        session = self.db.get(PatientSession, session_id)
        if session is None or _aware(session.expires_at) < utcnow():
            raise NotFound
        if not token or not token_matches(token, session.token_hash):
            raise Forbidden
        return session

    def delete(self, session: PatientSession) -> None:
        self.db.delete(session)
        self.db.commit()

    # --- диалог ------------------------------------------------------------
    @staticmethod
    def build_state(session: PatientSession) -> dialog.DialogState:
        return dialog.DialogState(
            {a.step_id: dialog.Answer.from_dict(a.payload) for a in session.answers},
            profile_available=bool(session.profile),
        )

    @staticmethod
    def _append(session: PatientSession, state: dialog.DialogState, step_id: str, answer: dialog.Answer) -> None:
        seq = (session.answers[-1].seq + 1) if session.answers else 1
        session.answers.append(SessionAnswer(seq=seq, step_id=step_id, payload=answer.to_dict()))
        state.answers[step_id] = answer

    def answer(self, session: PatientSession, data: schemas.AnswerIn) -> PatientSession:
        if session.status != dialog.Status.ACTIVE.value:
            raise Conflict("Опрос уже завершён. Чтобы изменить ответ, вернитесь назад.")
        state = self.build_state(session)
        answer = dialog.validate_answer(state, data.step_id, data.option_ids, data.text, data.skip)
        self._append(session, state, data.step_id, answer)
        if data.step_id == "for_whom" and answer.option_ids == ("self",):
            # Помощь нужна владельцу аккаунта: возраст и пол берём из профиля MAX.
            for step_id in PROFILE_STEPS:
                value = (session.profile or {}).get(step_id)
                if value:
                    self._append(session, state, step_id, dialog.Answer((value,), prefilled=True))
        self._apply_evaluation(session, state, last_step=data.step_id)
        return session

    def back(self, session: PatientSession) -> PatientSession:
        if not session.answers:
            raise Conflict("Это первый вопрос.")
        # Подставленные из профиля ответы откатываются вместе с ответом, который их вызвал.
        while session.answers and session.answers[-1].payload.get("prefilled"):
            session.answers.pop()
        session.answers.pop()  # delete-orphan удалит запись из БД
        self._apply_evaluation(session, self.build_state(session), last_step=None)
        return session

    def _apply_evaluation(self, session: PatientSession, state: dialog.DialogState, last_step: str | None) -> None:
        evaluation = dialog.evaluate(state)
        session.status = evaluation.status.value
        session.expires_at = utcnow() + self.ttl
        session.result = None
        self.db.flush()

        if evaluation.status == dialog.Status.EMERGENCY:
            recorded = {e.red_flag_code for e in session.emergency_events}
            for flag in evaluation.red_flags:
                if flag.code not in recorded and last_step:
                    session.emergency_events.append(EmergencyEvent(red_flag_code=flag.code, step_id=last_step))
            recommendation = triage.build_emergency(evaluation.red_flags)
        elif evaluation.status == dialog.Status.COMPLETED:
            recommendation = triage.build_recommendation(state)
        else:
            recommendation = None

        if recommendation:
            session.result = TriageResult(
                urgency=recommendation.urgency.value,
                care_place=recommendation.care_place.value,
                specialty=recommendation.specialty,
                payload=recommendation.to_dict(),
            )
        self.db.commit()

    # --- представление -----------------------------------------------------
    def view(self, session: PatientSession) -> schemas.SessionView:
        state = self.build_state(session)
        evaluation = dialog.evaluate(state)
        question = evaluation.question
        history = [
            schemas.HistoryItem(
                step_id=a.step_id,
                question=dialog.get_question(a.step_id, state).text,
                answer=dialog.answer_label(a.step_id, dialog.Answer.from_dict(a.payload), state),
            )
            for a in session.answers
        ]
        emergency = None
        if evaluation.status == dialog.Status.EMERGENCY:
            emergency = schemas.EmergencyOut(
                message=EMERGENCY_MESSAGE,
                flags=[schemas.RedFlagOut(code=f.code, title=f.title, explanation=f.explanation)
                       for f in evaluation.red_flags],
                advice=list(EMERGENCY_ADVICE),
            )
        recommendation = None
        if session.result is not None:
            rec = triage.Recommendation.from_dict(session.result.payload)
            recommendation = schemas.RecommendationOut(
                specialty=rec.specialty,
                urgency=rec.urgency.value,
                urgency_label=triage.URGENCY_LABELS[rec.urgency],
                care_place=rec.care_place.value,
                care_place_label=triage.CARE_PLACE_LABELS[rec.care_place],
                alternatives=[triage.CARE_PLACE_LABELS[a] for a in rec.alternatives],
                rationale=rec.rationale,
                advice=rec.advice,
            )
        total = max(evaluation.total, 1)
        answered = total if evaluation.status == dialog.Status.COMPLETED else evaluation.answered
        return schemas.SessionView(
            session_id=session.id,
            status=evaluation.status.value,
            question=schemas.QuestionOut(
                id=question.id,
                text=question.text,
                type=question.qtype.value,
                block=question.block,
                hint=question.hint,
                options=[schemas.OptionOut(id=o.id, label=o.label, exclusive=o.exclusive) for o in question.options],
                allow_text=question.allow_text,
                text_placeholder=question.text_placeholder,
                optional=question.optional,
            ) if question else None,
            progress=schemas.ProgressOut(answered=answered, total=total, percent=round(100 * answered / total)),
            history=history,
            can_go_back=bool(session.answers),
            emergency=emergency,
            recommendation=recommendation,
            disclaimer_start=DISCLAIMER_START,
            disclaimer_end=DISCLAIMER_END,
            expires_at=session.expires_at,
        )


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Удаляет просроченные сессии вместе со всеми ответами (минимизация хранения ПДн)."""
    now = now or utcnow()
    ids = list(db.scalars(select(PatientSession.id).where(PatientSession.expires_at < now)))
    if ids:
        for model in (SessionAnswer, TriageResult, EmergencyEvent):
            db.execute(delete(model).where(model.session_id.in_(ids)))
        db.execute(delete(PatientSession).where(PatientSession.id.in_(ids)))
        db.commit()
    return len(ids)
