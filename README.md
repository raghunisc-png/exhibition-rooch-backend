# Exhibition Invoice API — Backend

The API used by the [frontend](../frontend) PWA. Sales agents log in, submit customer +
product details captured at an exhibition booth, and the backend generates an invoice
PDF and delivers it to the customer over WhatsApp (falling back to SMS) via Twilio.

## Tech stack

| Concern | Technology |
|---|---|
| Language | Python 3.12 |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) (served by [Uvicorn](https://www.uvicorn.org/)) |
| Database | PostgreSQL, via [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (ORM) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| Validation / settings | [Pydantic v2](https://docs.pydantic.dev/) + `pydantic-settings` |
| Auth | JWT access tokens (`python-jose`) + `bcrypt` password hashing |
| Messaging | [Twilio](https://www.twilio.com/docs/whatsapp) (WhatsApp + SMS) |
| PDF generation | [ReportLab](https://www.reportlab.com/) |
| File storage | Local disk by default, or S3 (via `boto3`) — pluggable, see `app/services/storage.py` |
| Tests | `pytest` + `httpx` against an isolated SQLite DB |
| Containerization | Docker |

This is one of three independent git repositories for this project. See the
[root README](../README.md) for how it fits together with the [frontend](../frontend)
and for running everything together via `docker-compose`.

## How the app is structured

```
app/
  main.py              FastAPI app setup: CORS, routers, static file mount for
                        uploaded photos/PDFs at /files, /health check
  config.py             Settings loaded from environment variables / .env
                        (pydantic-settings) — see "Environment variables" below
  database.py            SQLAlchemy engine/session + declarative Base
  models.py               ORM models: Agent, Invoice, MessageLog
  schemas.py               Pydantic request/response models
  security.py              Password hashing (bcrypt) + JWT create/decode
  deps.py                   FastAPI dependencies: get_current_agent, require_admin
  create_admin.py            CLI script to create the first admin account
  routers/
    auth.py                    POST /api/auth/login, GET /api/auth/me,
                                admin-only agent management endpoints
    invoices.py                 CRUD for invoices created while online
                                 (multipart form + photo upload)
    sync.py                      POST /api/sync/invoices — batch endpoint the
                                 frontend calls to flush invoices that were
                                 queued locally while the device was offline
  services/
    invoice_service.py           Orchestrates: save invoice -> generate PDF ->
                                 send via messaging -> log the attempt
    numbering.py                  Generates sequential invoice numbers
    pdf.py                          Renders the invoice PDF (ReportLab)
    messaging.py                    Sends the PDF link via Twilio WhatsApp/SMS
    storage.py                      Saves uploaded photos/PDFs — local disk or S3
                                    depending on STORAGE_BACKEND
alembic/                Database migrations (alembic.ini + alembic/versions/)
tests/                  pytest suite, runs against SQLite, no external services needed
uploads/                Local file storage default location (photos, invoice PDFs) —
                        gitignored, created automatically
```

### Request flow for creating an invoice

1. Agent logs in (`POST /api/auth/login`) and gets a JWT, sent as
   `Authorization: Bearer <token>` on every subsequent request (see `deps.get_current_agent`).
2. **Online path:** agent submits the form directly to `POST /api/invoices` (multipart,
   with an optional photo).
3. **Offline path:** the frontend queues invoices locally and later batch-submits them to
   `POST /api/sync/invoices`.
4. Either way, `app/services/invoice_service.create_and_deliver` does the actual work:
   assigns an invoice number (`numbering.py`), saves the row, renders a PDF (`pdf.py`),
   uploads the photo/PDF (`storage.py`), and sends the customer a WhatsApp/SMS message
   with a link to it (`messaging.py`), logging the attempt in `MessageLog`.
5. Every invoice carries a `client_uuid` generated on the device. Both the online and
   sync endpoints treat it as an idempotency key — submitting the same invoice twice
   (e.g. a retried sync after a dropped connection) is a no-op, not a duplicate.

### Auth model

Two roles: `admin` and `agent` (see `AgentRole` in `models.py`). Regular agents only see
their own invoices; admins see everything and can create new agent accounts
(`POST /api/auth/agents`, gated by `deps.require_admin`). There's no self-serve sign-up —
the first admin account is created via the `create_admin` CLI script (below), and admins
create further accounts through the API/UI after that.

## Prerequisites

- Python 3.12 (matches the Docker image; slightly older 3.11/3.10 will likely also work
  but isn't what's tested)
- PostgreSQL 16 running locally (or use the `db` service in the root
  [`docker-compose.yml`](../docker-compose.yml) instead of installing Postgres yourself)
- (Optional, for real message delivery) A Twilio account with WhatsApp/SMS enabled —
  without it, invoices are still created and PDFs generated, they just won't be sent
  (`messaging_configured` in `config.py` checks for Twilio credentials)

## Local setup (without Docker)

```bash
# from the backend/ directory
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit values — see table below
export $(grep -v '^#' .env | xargs)   # or use direnv / python-dotenv instead

alembic upgrade head             # creates/updates all tables
python -m app.create_admin "Jane Doe" jane@example.com "StrongPass123"
python -m app.create_admin "Rooch Admin" admin@rooch.in "Rooch@123"


uvicorn app.main:app --reload
```

The API is now running at **http://localhost:8000**, with interactive docs at
**http://localhost:8000/docs** (Swagger UI, auto-generated from the FastAPI routes —
use it to try endpoints without needing the frontend running).

> `pydantic-settings` (see `config.py`, `env_file=".env"`) reads `.env` from the current
> working directory, so keep it in `backend/` (as above) rather than the repo root when
> running the API directly.

## Database migrations

This project uses Alembic. The most common commands:

```bash
alembic upgrade head                        # apply all pending migrations
alembic revision --autogenerate -m "..."    # generate a new migration after
                                             # changing app/models.py
alembic downgrade -1                        # roll back the last migration
```

Migration files live in `alembic/versions/`. Always review autogenerated migrations
before committing — Alembic doesn't catch every kind of change reliably (e.g. column
renames look like a drop + add).

## Tests

```bash
pytest -q
```

Tests run against an isolated SQLite database (`tests/conftest.py` sets `DATABASE_URL`
to a local `sqlite:///./test.db` before the app is imported, and creates/drops all
tables around each test) — no Postgres, Twilio, or `.env` file required. Safe to run
immediately after `pip install -r requirements.txt`.

## Environment variables

All settings are defined in `app/config.py` (with defaults suitable for local dev). Copy
[`.env.example`](.env.example) to `.env` and fill in real values. The important ones:

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `development` | `development` \| `production` \| `test` |
| `DATABASE_URL` | `postgresql+psycopg://expo_user:expo_pass@localhost:5432/expo_invoices` | SQLAlchemy connection string |
| `JWT_SECRET_KEY` | `insecure-dev-secret-change-me` | **Must** be overridden with a strong secret outside local dev |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` (12h) | JWT lifetime |
| `STORAGE_BACKEND` | `local` | `local` (saves to `UPLOAD_DIR`) or `s3` |
| `UPLOAD_DIR` | `uploads` | Where photos/PDFs are saved when `STORAGE_BACKEND=local` |
| `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_ENDPOINT_URL` | empty | Only needed when `STORAGE_BACKEND=s3` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base URL used when building links to uploaded files sent to customers |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` | empty | Twilio credentials; leave empty to disable actual message sending |
| `TWILIO_WHATSAPP_FROM`, `TWILIO_SMS_FROM` | Twilio sandbox numbers | Sender numbers |
| `COMPANY_NAME`, `COMPANY_ADDRESS`, `COMPANY_GSTIN` | `Rooch Fashions` / empty | Printed on the generated invoice PDF |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list of allowed frontend origins |

## Running with Docker

```bash
docker build -t exhibition-backend .
docker run -p 8000:8000 --env-file .env exhibition-backend
```

The container image (`python:3.12-slim`) installs `requirements.txt`, then on startup
runs `alembic upgrade head` before starting Uvicorn — migrations are applied
automatically on every container start, so you don't run them manually in this path.

More commonly, run everything together (Postgres + backend + frontend) via
`docker-compose` from the [repo root](../docker-compose.yml):

```bash
cd ..
docker compose up --build
```

## Notes for first-time contributors

- Business logic belongs in `app/services/`, not in the routers — routers should mainly
  validate input and call a service function. Look at `invoice_service.create_and_deliver`
  as the reference for how a new mutating endpoint should be structured.
- If you add/change a column on a model in `app/models.py`, you must also generate an
  Alembic migration (`alembic revision --autogenerate -m "..."`) — the app does not
  create/alter tables automatically outside of tests.
- `client_uuid` idempotency (see `models.Invoice`) is the key mechanism keeping offline
  sync safe — don't bypass it when touching invoice-creation code.
- `uploads/` is local scratch storage and is gitignored; don't commit anything there.
- API docs at `/docs` (Swagger) and `/redoc` are the fastest way to explore available
  endpoints and try requests while developing the frontend against this backend.
