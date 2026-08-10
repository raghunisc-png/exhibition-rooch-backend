"""
Human-friendly invoice number generation.

Format:

    INV-YYYYMMDD-####

Examples:

    INV-20260810-0001
    INV-20260810-0002
    INV-20260810-0003

The invoice number is unique because `invoices.invoice_number`
has a database-level unique constraint.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Invoice


# ============================================================
# INVOICE NUMBER
# ============================================================


def generate_invoice_number(
    db: Session,
) -> str:
    """
    Generate the next human-friendly invoice number for today.

    Format:

        INV-YYYYMMDD-####

    The sequence is calculated from the number of invoices
    already created for the current day.

    Example:

        Existing:
            INV-20260810-0001
            INV-20260810-0002

        New:
            INV-20260810-0003
    """

    # --------------------------------------------------------
    # Today's prefix
    # --------------------------------------------------------

    today_prefix = (
        f"INV-{datetime.utcnow():%Y%m%d}-"
    )

    # --------------------------------------------------------
    # Count today's invoices
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Generate next number
    # --------------------------------------------------------

    return (
        f"{today_prefix}"
        f"{count_today + 1:04d}"
    )