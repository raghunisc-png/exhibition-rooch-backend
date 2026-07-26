"""
One-off CLI to create the first admin agent account.

Usage (from the backend/ directory, with the venv active and DATABASE_URL
set / migrations applied):

    python -m app.create_admin "Jane Doe" jane@example.com "StrongPass123"
"""
import sys

from app.database import SessionLocal
from app.models import Agent, AgentRole
from app.security import hash_password


def main():
    if len(sys.argv) != 4:
        print("Usage: python -m app.create_admin <full_name> <email> <password>")
        raise SystemExit(1)

    full_name, email, password = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
    db = SessionLocal()
    try:
        if db.query(Agent).filter(Agent.email == email).first():
            print(f"Agent with email {email} already exists.")
            raise SystemExit(1)

        agent = Agent(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role=AgentRole.admin,
            booth_name="HQ",
        )
        db.add(agent)
        db.commit()
        print(f"Created admin agent: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
