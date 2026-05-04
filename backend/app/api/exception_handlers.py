"""
Глобальные обработчики исключений FastAPI (единый JSON для клиентов + OpenAPI-friendly errors).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.ai.orchestration.errors import PipelineError, PipelineValidationBlockedError


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует обработчики на экземпляре приложения."""

    @app.exception_handler(PipelineValidationBlockedError)
    async def _validation_blocked(_: Request, exc: PipelineValidationBlockedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "pipeline_validation_blocked",
                "message": str(exc),
                "reasons": list(exc.reasons),
            },
        )

    @app.exception_handler(PipelineError)
    async def _pipeline_error(_: Request, exc: PipelineError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": "pipeline_error", "message": str(exc)},
        )
