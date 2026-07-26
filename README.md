# Exhibition Invoice API (backend)

FastAPI + PostgreSQL backend for capturing booth sales and delivering
invoices over WhatsApp/SMS via Twilio. See the repo root README for the
full-stack setup and deployment guide.

## Local dev (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then edit values
export $(grep -v '^#' ../.env | xargs)   # or use direnv/python-dotenv
alembic upgrade head
python -m app.create_admin "Jane Doe" jane@example.com "StrongPass123"
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Tests

```bash
pytest -q
```

Tests run against an isolated SQLite DB and don't require Postgres or Twilio.
