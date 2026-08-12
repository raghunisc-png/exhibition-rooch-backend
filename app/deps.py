"""
Shared FastAPI dependencies.

Provides:

- OAuth2 bearer-token extraction
- Current authenticated agent
- Admin-only access dependency
"""

from __future__ import annotations

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Agent
from app.security import decode_access_token


# ============================================================
# OAUTH2
# ============================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login"
)


# ============================================================
# AUTHENTICATED AGENT
# ============================================================

def get_current_agent(
    token: str = Depends(
        oauth2_scheme
    ),
    db: Session = Depends(
        get_db
    ),
) -> Agent:
    """
    Resolve the currently authenticated agent.

    The JWT must contain:

        sub = agent ID

    Inactive or nonexistent agents are rejected.
    """

    credentials_error = HTTPException(
        status_code=(
            status.HTTP_401_UNAUTHORIZED
        ),
        detail="Could not validate credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    # --------------------------------------------------------
    # Decode token
    # --------------------------------------------------------

    try:

        payload = decode_access_token(
            token
        )

    except (ValueError, TypeError):

        raise credentials_error

    # --------------------------------------------------------
    # Extract subject
    # --------------------------------------------------------

    agent_id = payload.get(
        "sub"
    )

    if agent_id is None:

        raise credentials_error

    # --------------------------------------------------------
    # Convert subject to integer
    # --------------------------------------------------------

    try:

        agent_id_int = int(
            agent_id
        )

    except (
        TypeError,
        ValueError,
    ):

        raise credentials_error

    # --------------------------------------------------------
    # Load agent
    # --------------------------------------------------------

    agent = db.get(
        Agent,
        agent_id_int,
    )

    if (
        agent is None
        or not agent.is_active
    ):

        raise credentials_error

    return agent


# ============================================================
# ADMIN
# ============================================================

def require_admin(
    agent: Agent = Depends(
        get_current_agent
    ),
) -> Agent:
    """
    Require the authenticated agent to have admin role.
    """

    if agent.role != "admin":

        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Admin access required",
        )

    return agent