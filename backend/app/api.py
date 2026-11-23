# проверены HTTP-эндпоинты и коды ошибок
"""HTTP API (версия v1)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import schemas
from .db import get_db
from .domain.dialog import DialogError
from .integrations.max_gateway import (
    CoreClient,
    CoreUnauthorized,
    CoreUnavailable,
    CoreUserNotFound,
    age_group,
    get_core_client,
)
from .models import PatientSession
from .services import Conflict, Forbidden, NotFound, SessionService

ERR_SESSION_NOT_FOUND = "Сессия не найдена или истекла. Начните заново."
ERR_ACCESS_DENIED = "Нет доступа к сессии."
router = APIRouter(prefix="/api/v1")


def _service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(db)


def _authorized(
    session_id: uuid.UUID,
    x_session_token: str | None = Header(default=None),
    service: SessionService = Depends(_service),
) -> PatientSession:
    try:
        return service.get_authorized(session_id, x_session_token)
    except NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ERR_SESSION_NOT_FOUND)
    except Forbidden:
        raise HTTPException(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/sessions", response_model=schemas.SessionCreatedOut, status_code=201, tags=["dialog"])
def create_session(body: schemas.SessionCreateIn, service: SessionService = Depends(_service)):
    session, token = service.create(channel=body.channel)
    return schemas.SessionCreatedOut(**service.view(session).model_dump(), session_token=token)


@router.get("/sessions/{session_id}", response_model=schemas.SessionView, tags=["dialog"])
def get_session(session: PatientSession = Depends(_authorized), service: SessionService = Depends(_service)):
    return service.view(session)


@router.post("/sessions/{session_id}/answers", response_model=schemas.SessionView, tags=["dialog"])
def post_answer(
    body: schemas.AnswerIn,
    session: PatientSession = Depends(_authorized),
    service: SessionService = Depends(_service),
):
    try:
        service.answer(session, body)
    except DialogError as exc:
        raise HTTPException(422, str(exc))
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return service.view(session)


@router.post("/sessions/{session_id}/back", response_model=schemas.SessionView, tags=["dialog"])
def go_back(session: PatientSession = Depends(_authorized), service: SessionService = Depends(_service)):
    try:
        service.back(session)
    except Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return service.view(session)


@router.delete("/sessions/{session_id}", status_code=204, tags=["dialog"])
def delete_session(session: PatientSession = Depends(_authorized), service: SessionService = Depends(_service)):
    """Право пользователя на удаление своих данных (ФЗ-152, ст. 21)."""
    service.delete(session)
    return Response(status_code=204)


# --- Вход из мини-приложения MAX -------------------------------------------
@router.post("/integrations/max/auth", response_model=schemas.SessionCreatedOut, status_code=201, tags=["max"])
def max_auth(
    body: schemas.MaxAuthIn,
    core: CoreClient = Depends(get_core_client),
    service: SessionService = Depends(_service),
):
    """Обменивает 5-минутный JWT пользователя из URL мини-приложения на собственную сессию."""
    try:
        user = core.fetch_user(body.token)
    except CoreUnauthorized:
        raise HTTPException(401, "Ссылка устарела. Откройте сервис из бота MAX ещё раз.")
    except CoreUserNotFound:
        raise HTTPException(404, "Пользователь MAX не найден. Откройте сервис из бота ещё раз.")
    except CoreUnavailable:
        raise HTTPException(502, "Сервис авторизации MAX временно недоступен. Попробуйте позже.")

    session, token = service.create(
        channel="max",
        external_user_id=user.user_id,
        profile={"age_group": age_group(user.birth_date), "sex": user.sex},
    )
    view = service.view(session)
    return schemas.SessionCreatedOut(**view.model_dump(), session_token=token, greeting_name=user.first_name)
