"""
Batch sync endpoint for invoices captured while the agent's device was
offline. The client (PWA) queues invoices locally in IndexedDB, each tagged
with a client-generated UUID, and POSTs them here in a batch once back
online. Each item is idempotent on client_uuid so retried/duplicate syncs
(e.g. connection drops mid-batch) never create duplicate invoices.
"""
from __future__ import annotations

import base64
import binascii
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent
from app.models import Agent, Invoice
from app.schemas import SyncRequest, SyncResponse, SyncResultItem
from app.services import storage
from app.services.invoice_service import create_and_deliver

logger = logging.getLogger("sync")
router = APIRouter(prefix="/api/sync", tags=["sync"])

MAX_PHOTO_BYTES = 8 * 1024 * 1024
EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}


@router.post("/invoices", response_model=SyncResponse)
def sync_invoices(
    payload: SyncRequest,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    results: list[SyncResultItem] = []

    for item in payload.items:
        existing = db.query(Invoice).filter(Invoice.client_uuid == item.client_uuid).first()
        if existing:
            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="duplicate",
                    invoice_id=existing.id,
                    invoice_number=existing.invoice_number,
                )
            )
            continue

        try:
            photo_path = None
            if item.photo_base64:
                raw = base64.b64decode(item.photo_base64, validate=True)
                if len(raw) > MAX_PHOTO_BYTES:
                    raise ValueError("Photo exceeds 8MB limit")
                ext = EXT_BY_CONTENT_TYPE.get(item.photo_content_type or "", ".jpg")
                import uuid as _uuid

                photo_path = storage.save_bytes(raw, "photos", f"{_uuid.uuid4().hex}{ext}")

            data = item.model_dump(exclude={"client_uuid", "photo_base64", "photo_content_type"})
            invoice = create_and_deliver(db, agent, {"client_uuid": item.client_uuid, **data}, photo_path)
            results.append(
                SyncResultItem(
                    client_uuid=item.client_uuid,
                    status="created",
                    invoice_id=invoice.id,
                    invoice_number=invoice.invoice_number,
                )
            )
        except (binascii.Error, ValueError) as exc:
            db.rollback()
            results.append(SyncResultItem(client_uuid=item.client_uuid, status="error", error=str(exc)))
        except Exception:
            db.rollback()
            logger.exception("Failed to sync invoice %s", item.client_uuid)
            results.append(
                SyncResultItem(client_uuid=item.client_uuid, status="error", error="Server error while syncing")
            )

    return SyncResponse(results=results)
