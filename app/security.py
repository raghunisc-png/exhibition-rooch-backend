"""
Password hashing and JWT authentication helpers.

Provides:

- Password hashing
- Password verification
- Access-token creation
- Access-token decoding
"""

from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings


# ============================================================
# CONFIG
# ============================================================

settings = get_settings()


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(
    password: str,
) -> str:
    """
    Hash a plaintext password using bcrypt.
    """

    if not password:
        raise ValueError(
            "Password cannot be empty."
        )

    password_bytes = password.encode(
        "utf-8"
    )

    password_hash = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    )

    return password_hash.decode(
        "utf-8"
    )


# ============================================================
# PASSWORD VERIFICATION
# ============================================================

def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """
    Verify a plaintext password against
    a stored bcrypt password hash.
    """

    if not password or not password_hash:
        return False

    try:

        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )

    except (
        ValueError,
        TypeError,
    ):

        return False


# ============================================================
# CREATE ACCESS TOKEN
# ============================================================

def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a signed JWT access token.

    The `sub` claim identifies the authenticated agent.
    """

    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=(
                settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        )
    )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
    }

    if extra_claims:
        payload.update(
            extra_claims
        )

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# ============================================================
# DECODE ACCESS TOKEN
# ============================================================

def decode_access_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate an access token.

    Raises:
        ValueError:
            When the token is invalid or expired.
    """

    if not token:
        raise ValueError(
            "Access token is required."
        )

    try:

        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[
                settings.JWT_ALGORITHM
            ],
        )

    except (
        JWTError,
        ValueError,
        TypeError,
    ) as exc:

        raise ValueError(
            "Invalid or expired token"
        ) from exc

    return payload