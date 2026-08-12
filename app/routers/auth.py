"""
Agent authentication and admin agent management.

Routes:

    POST /api/auth/login
    GET  /api/auth/me
    POST /api/auth/agents
    GET  /api/auth/agents
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import (
    get_current_agent,
    require_admin,
)
from app.models import Agent
from app.schemas import (
    AgentCreate,
    AgentOut,
    LoginRequest,
    TokenResponse,
)
from app.security import (
    create_access_token,
    hash_password,
    verify_password,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


# ============================================================
# LOGIN
# ============================================================

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate an agent and return a JWT access token.
    """

    email = payload.email.lower().strip()

    agent = (
        db.query(Agent)
        .filter(
            Agent.email == email
        )
        .first()
    )

    # --------------------------------------------------------
    # Invalid credentials
    # --------------------------------------------------------

    if not agent:

        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid email or password",
        )

    if not verify_password(
        payload.password,
        agent.password_hash,
    ):

        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid email or password",
        )

    # --------------------------------------------------------
    # Disabled account
    # --------------------------------------------------------

    if not agent.is_active:

        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Account is disabled",
        )

    # --------------------------------------------------------
    # JWT
    # --------------------------------------------------------

    token = create_access_token(
        subject=str(agent.id),
        extra_claims={
            "role": agent.role.value
            if hasattr(
                agent.role,
                "value",
            )
            else str(agent.role),
        },
    )

    return TokenResponse(
        access_token=token,
        agent=AgentOut.model_validate(
            agent
        ),
    )


# ============================================================
# CURRENT AGENT
# ============================================================

@router.get(
    "/me",
    response_model=AgentOut,
)
def me(
    current: Agent = Depends(
        get_current_agent
    ),
) -> AgentOut:
    """
    Return the currently authenticated agent.
    """

    return AgentOut.model_validate(
        current
    )


# ============================================================
# CREATE AGENT
# ============================================================

@router.post(
    "/agents",
    response_model=AgentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    _: Agent = Depends(require_admin),
) -> AgentOut:
    """
    Create a new booth agent.

    Only administrators can create agents.
    """

    email = payload.email.lower().strip()

    # --------------------------------------------------------
    # Validate role
    # --------------------------------------------------------

    role = payload.role.strip().lower()

    if role not in {
        "admin",
        "agent",
    }:

        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Role must be either "
                "'admin' or 'agent'."
            ),
        )

    # --------------------------------------------------------
    # Duplicate email
    # --------------------------------------------------------

    existing = (
        db.query(Agent)
        .filter(
            Agent.email == email
        )
        .first()
    )

    if existing:

        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail=(
                "An agent with this email "
                "already exists"
            ),
        )

    # --------------------------------------------------------
    # Create agent
    # --------------------------------------------------------

    agent = Agent(
        full_name=payload.full_name,
        email=email,
        password_hash=hash_password(
            payload.password
        ),
        booth_name=payload.booth_name,
        role=role,
    )

    db.add(agent)

    try:

        db.commit()

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to create agent.",
        )

    db.refresh(agent)

    return AgentOut.model_validate(
        agent
    )


# ============================================================
# LIST AGENTS
# ============================================================

@router.get(
    "/agents",
    response_model=list[AgentOut],
)
def list_agents(
    db: Session = Depends(get_db),
    _: Agent = Depends(
        require_admin
    ),
) -> list[AgentOut]:
    """
    List all booth agents.

    Only administrators can access this endpoint.
    """

    return (
        db.query(Agent)
        .order_by(
            Agent.full_name
        )
        .all()
    )