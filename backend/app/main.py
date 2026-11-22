"""Точка входа FastAPI."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (регистрация моделей)
from .api import router
from .config import get_settings
from .db import Base, SessionLocal, engine
from .services import purge_expired

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("medmarshrut")



async def _purge_loop(interval_minutes: int) -> None:
    while True:
        with contextlib.suppress(Exception):
            with SessionLocal() as db:
                removed = purge_expired(db)
                if removed:
                    log.info("Удалено просроченных сессий: %s", removed)
        await asyncio.sleep(interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    task = asyncio.create_task(_purge_loop(get_settings().purge_interval_minutes))
    yield
    task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="МедМаршрут API",
        version="1.0.0",
        description="Первичная маршрутизация пациента. Сервис не ставит диагноз и не заменяет врача.",
        lifespan=lifespan,
    )
    
    import logging
    import time
    from fastapi import Request

    logger = logging.getLogger("uvicorn.error")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()

        logger.info(
            "Incoming %s %s",
            request.method,
            request.url.path
        )

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled error: %s %s",
                request.method,
                request.url.path
            )
            raise

        duration = time.perf_counter() - start

        logger.info(
            "Completed %s %s status=%s duration=%.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration
        )

        return response
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Session-Token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"  # медицинские данные не кешируются
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.include_router(router)
    return app


app = create_app()
