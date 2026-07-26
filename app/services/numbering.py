"""Human-friendly, sequential-looking invoice number generation."""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Invoice


def generate_invoice_number(db: Session) -> str:
    """
    Format: INV-YYYYMMDD-#### where #### is a per-day sequence.
    Computed inside the same transaction as the insert; the unique index on
    invoice_number is the final safety net against races.
    """
    today_prefix = f"INV-{datetime.utcnow():%Y%m%d}-"
    count_today = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.invoice_number.like(f"{today_prefix}%"))
        .scalar()
        or 0
    )
    return f"{today_prefix}{count_today + 1:04d}"
