"""
Main FastAPI application.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import get_settings
from app.routers import auth, invoices, sync


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger("invoice_api")


# ============================================================
# CONFIG
# ============================================================

settings = get_settings()


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Exhibition Invoice API",
    description=(
        "Capture customer + product details at exhibition "
        "booths and deliver invoices via WhatsApp/SMS."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(sync.router)


# ============================================================
# VALIDATION ERROR HANDLERS
# ============================================================

@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Return clean FastAPI validation errors as JSON.
    """

    errors = exc.errors()

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": jsonable_encoder(errors),
        },
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(
    request: Request,
    exc: ValidationError,
):
    """
    Handle Pydantic ValidationError exceptions raised manually
    inside endpoint/service code.
    """

    raw_errors = exc.errors(
        include_url=False,
    )

    for error in raw_errors:
        error.pop("ctx", None)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": jsonable_encoder(raw_errors),
        },
    )


# ============================================================
# LOCAL FILE STORAGE
# ============================================================

if settings.STORAGE_BACKEND == "local":

    upload_dir = Path(
        settings.UPLOAD_DIR
    ).resolve()

    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app.mount(
        "/files",
        StaticFiles(
            directory=str(upload_dir),
        ),
        name="files",
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health() -> dict[str, str]:
    """
    Basic health check.
    """

    return {
        "status": "ok",
    }


# ============================================================
# DEBUG ROUTES
# ============================================================

@app.get("/api/debug/routes")
def debug_routes() -> list[dict[str, str]]:
    """
    Show every route currently registered in FastAPI.

    Development/debugging endpoint.
    """

    routes = []

    for route in app.routes:

        methods = getattr(
            route,
            "methods",
            None,
        )

        routes.append(
            {
                "path": route.path,
                "methods": ",".join(
                    sorted(methods or [])
                ),
                "name": route.name,
            }
        )

    return routes