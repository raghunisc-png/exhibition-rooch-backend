"""Shared FastAPI dependencies."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Agent
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_agent(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Agent:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise credentials_error

    agent_id = payload.get("sub")
    if agent_id is None:
        raise credentials_error

    agent = db.get(Agent, int(agent_id))
    if agent is None or not agent.is_active:
        raise credentials_error
    return agent


def require_admin(agent: Agent = Depends(get_current_agent)) -> Agent:
    if agent.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return agent
