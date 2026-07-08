"""FastAPI application entry — P1-01."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import browse, factor, health, industry, stock
from app.core.config import settings
from app.core.envelope import fail
from app.core.errors import NotFoundError, ValidationError
from app.services.scheduler import build_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.start()
        logger.info("APScheduler started")
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            logger.info("APScheduler stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=200,
            content=fail(exc.code, str(exc)),
        )

    @app.exception_handler(ValidationError)
    async def _handle_validation(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=200,
            content=fail(exc.code, str(exc), detail=exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_fastapi_validation(request: Request, exc: RequestValidationError):
        """Map FastAPI's Query/Path validation errors to our envelope."""
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(
            status_code=200,
            content=fail(
                "VALIDATION_INVALID_PARAMETER",
                str(first.get("msg", "invalid parameter")),
                detail={"errors": exc.errors()},
            ),
        )

    app.include_router(health.router)
    app.include_router(industry.router)
    app.include_router(browse.router)
    app.include_router(stock.router)
    app.include_router(factor.router)
    return app


app = create_app()
