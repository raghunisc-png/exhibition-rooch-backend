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

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="Exhibition Invoice API",
    description="Capture customer + product details at exhibition booths and deliver invoices via WhatsApp/SMS.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(sync.router)


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    """
    Endpoints that build a Pydantic model manually inside the function body
    (e.g. the multipart invoice-create endpoint) raise a raw pydantic
    ValidationError rather than FastAPI's own RequestValidationError. Convert
    it to the same 422 shape the frontend already expects.
    """
    raw_errors = exc.errors(include_url=False)
    for err in raw_errors:
        err.pop("ctx", None)
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": jsonable_encoder(raw_errors)})

# Serve uploaded photos + generated PDFs when using local storage. Behind a
# reverse proxy in production you'd typically let nginx/CDN serve this path
# directly instead, but mounting it here keeps a single-container deploy simple.
if settings.STORAGE_BACKEND == "local":
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(upload_dir)), name="files")


@app.get("/health")
def health():
    return {"status": "ok"}
