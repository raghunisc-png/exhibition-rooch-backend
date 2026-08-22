"""
Human-friendly invoice number generation.

Format:

    INV-YYYYMMDD-####

The database unique constraint on invoice_number remains the
final protection against duplicate invoice numbers.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Invoice


def generate_invoice_number(
    db: Session,
) -> str:
    """
    Generate the next invoice number for today.

    This function calculates the next number based on existing
    invoices. The unique database constraint remains the final
    concurrency protection.
    """

    today_prefix = (
        f"INV-{datetime.now():%Y%m%d}-"
    )

    count_today = (
        db.query(
            func.count(Invoice.id)
        )
        .filter(
            Invoice.invoice_number.like(
                f"{today_prefix}%"
            )
        )
        .scalar()
        or 0
    )

    return (
        f"{today_prefix}"
        f"{count_today + 1:04d}"
    )