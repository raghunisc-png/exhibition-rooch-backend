"""
Offline invoice batch synchronization.

The frontend stores invoices in IndexedDB while offline.

Each invoice has a client-generated UUID.

When connectivity returns:

    IndexedDB
        ↓
    POST /api/sync/invoices
        ↓
    Check client_uuid
        ↓
    Create if new
        ↓
    Return duplicate if already synced

Each invoice contains individually priced items.
"""

from __future__ import annotations

import base64
import binascii
import logging
import uuid as uuid_module

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent
from app.models import Agent, Invoice
from app.schemas import (
    SyncRequest,
    SyncResponse,
    SyncResultItem,
)
from app.services import storage
from app.services.invoice_service import create_and_deliver


logger = logging.getLogger("sync")


router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
)


# ============================================================
# CONSTANTS
# ============================================================

MAX_PHOTO_BYTES = 8 * 1024 * 1024


EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


ALLOWED_CONTENT_TYPES = set(
    EXT_BY_CONTENT_TYPE.keys()
)


# ============================================================
# SYNC INVOICES
# ============================================================

@router.post(
    "/invoices",
    response_model=SyncResponse,
)
def sync_invoices(
    payload: SyncRequest,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    """
    Synchronize invoices captured while offline.

    Every invoice is identified by client_uuid.

    If the invoice already exists:
        status = duplicate

    If it is successfully created:
        status = created

    If processing fails:
        status = error
    """

    results: list[SyncResultItem] = []

    # ========================================================
    # PROCESS EACH OFFLINE INVOICE
    # ========================================================

    for item in payload.items:

        # ----------------------------------------------------
        # IDEMPOTENCY CHECK
        # ----------------------------------------------------

        existing = (
            db.query(Invoice)
            .filter(
                Invoice.client_uuid
                == item.client_uuid
            )
            .first()
        )

        if existing:
            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="duplicate",
                    invoice_id=existing.id,
                    invoice_number=(
                        existing.invoice_number
                    ),
                )
            )

            continue

        # ----------------------------------------------------
        # PROCESS NEW INVOICE
        # ----------------------------------------------------

        try:

            # =================================================
            # PHOTO VALIDATION
            # =================================================

            if not item.photo_base64:
                raise ValueError(
                    "Product photo is required."
                )

            if (
                item.photo_content_type
                not in ALLOWED_CONTENT_TYPES
            ):
                raise ValueError(
                    "Unsupported photo content type."
                )

            # =================================================
            # DECODE BASE64 PHOTO
            # =================================================

            try:
                raw_photo = base64.b64decode(
                    item.photo_base64,
                    validate=True,
                )

            except (
                binascii.Error,
                ValueError,
            ) as exc:

                raise ValueError(
                    "Invalid product photo data."
                ) from exc

            # =================================================
            # PHOTO SIZE CHECK
            # =================================================

            if len(raw_photo) > MAX_PHOTO_BYTES:
                raise ValueError(
                    "Photo exceeds 8MB limit."
                )

            # Empty files should not be accepted.
            if len(raw_photo) == 0:
                raise ValueError(
                    "Product photo is empty."
                )

            # =================================================
            # SAVE PHOTO
            # =================================================

            extension = (
                EXT_BY_CONTENT_TYPE[
                    item.photo_content_type
                ]
            )

            filename = (
                f"{uuid_module.uuid4().hex}"
                f"{extension}"
            )

            photo_path = storage.save_bytes(
                raw_photo,
                "photos",
                filename,
            )

            # =================================================
            # PREPARE INVOICE DATA
            # =================================================

            data = item.model_dump(
                exclude={
                    "client_uuid",
                    "photo_base64",
                    "photo_content_type",
                }
            )

            # =================================================
            # CREATE INVOICE
            # =================================================

            invoice = create_and_deliver(
                db=db,
                agent=agent,
                data={
                    "client_uuid": (
                        item.client_uuid
                    ),
                    **data,
                },
                photo_relative_path=photo_path,
            )

            # =================================================
            # RESULT
            # =================================================

            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="created",
                    invoice_id=invoice.id,
                    invoice_number=(
                        invoice.invoice_number
                    ),
                )
            )

        # ====================================================
        # VALIDATION / PHOTO ERRORS
        # ====================================================

        except ValueError as exc:

            db.rollback()

            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="error",
                    error=str(exc),
                )
            )

        # ====================================================
        # UNEXPECTED SERVER ERROR
        # ====================================================

        except Exception:

            db.rollback()

            logger.exception(
                "Failed to sync invoice %s",
                item.client_uuid,
            )

            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="error",
                    error=(
                        "Server error while syncing"
                    ),
                )
            )

    # ========================================================
    # RESPONSE
    # ========================================================

    return SyncResponse(
        results=results
    )