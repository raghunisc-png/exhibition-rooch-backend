"""Agent authentication + admin agent management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_agent, require_admin
from app.models import Agent
from app.schemas import AgentCreate, AgentOut, LoginRequest, TokenResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.email == payload.email.lower()).first()
    if not agent or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not agent.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    token = create_access_token(subject=str(agent.id), extra_claims={"role": agent.role})
    return TokenResponse(access_token=token, agent=AgentOut.model_validate(agent))


@router.get("/me", response_model=AgentOut)
def me(current: Agent = Depends(get_current_agent)):
    return current


@router.post("/agents", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), _: Agent = Depends(require_admin)):
    existing = db.query(Agent).filter(Agent.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An agent with this email already exists")

    agent = Agent(
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        booth_name=payload.booth_name,
        role=payload.role,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), _: Agent = Depends(require_admin)):
    return db.query(Agent).order_by(Agent.full_name).all()
