import logging
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app.config import get_settings
from app.routers import auth, invoices, sync


# ============================================================
# CONFIG
# ============================================================

logging.basicConfig(level=logging.INFO)

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
# PYDANTIC VALIDATION ERROR HANDLER
# ============================================================

@app.exception_handler(ValidationError)
async def pydantic_validation_handler(
    request: Request,
    exc: ValidationError,
):
    """
    Endpoints that manually build Pydantic models inside the
    function body, such as the multipart invoice-create
    endpoint, can raise a raw Pydantic ValidationError.

    Convert it to a 422 response that the frontend can consume.
    """

    raw_errors = exc.errors(
        include_url=False
    )

    for error in raw_errors:
        error.pop("ctx", None)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": jsonable_encoder(
                raw_errors
            )
        },
    )


# ============================================================
# LOCAL FILE STORAGE
# ============================================================

if settings.STORAGE_BACKEND == "local":

    upload_dir = Path(
        settings.UPLOAD_DIR
    )

    upload_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app.mount(
        "/files",
        StaticFiles(
            directory=str(upload_dir)
        ),
        name="files",
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok"
    }