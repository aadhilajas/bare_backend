# Bare CRM — Backend

FastAPI backend for **Bare**, an AI-native mini CRM for a fictional skincare D2C brand. This repository contains the CRM API and the channel-stub service that simulates message delivery.

> **Repository note:** This is the **backend** repo (`bare_backend` on GitHub). The React frontend lives in a separate repository (`bare_frontend`). Push only the contents listed under [Repository contents](#repository-contents).

## Stack

| Component | Technology |
|---|---|
| CRM API | FastAPI + SQLModel + SQLite |
| Channel stub | FastAPI (separate service on port 8001) |
| Embedded simulator | In-process fallback inside `crm-backend` for single-service deploys |
| AI | OpenAI-compatible API (`gpt-4o-mini`, supports OpenRouter) |

## Services

| Service | Port | Purpose |
|---|---|---|
| `crm-backend` | 8000 (or `$PORT`) | CRM API — customers, segments, campaigns, analytics, AI co-pilot |
| `channel-stub` | 8001 | Simulates WhatsApp/SMS/email delivery and posts receipts back to the CRM |

## Repository contents

```
├── crm-backend/       # CRM API service
├── channel-stub/      # Delivery simulation service (Docker Compose / two-service deploy)
├── docker-compose.yml
├── .gitignore
└── README.md
```

Do **not** include `docs/`, `frontend/`, `.cursorrules`, or any local `.env` files.

## Prerequisites

- Python 3.12+ (Docker images use 3.12)
- pip
- Docker & Docker Compose (optional, for containerised run)

## Local setup (without Docker)

### 1. CRM backend

```bash
cd crm-backend
pip install -r requirements.txt
cp .env.example .env          # then add your OPENAI_API_KEY
python -m uvicorn main:app --reload --port 8000
```

On first startup the API **auto-seeds** demo data when the database has no customers (`seed_if_empty()` in `main.py`). To reset or re-seed manually:

```bash
python seed/generate.py       # WARNING: wipes all existing data first
```

### 2. Channel stub (separate terminal)

Required for local campaign delivery simulation via HTTP (Docker Compose runs this automatically):

```bash
cd channel-stub
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

### 3. Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

## Environment variables

### `crm-backend/.env`

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | For AI features | — | OpenAI or OpenRouter API key |
| `CHANNEL_STUB_URL` | No | `http://localhost:8001` | Channel stub base URL |
| `EMBEDDED_CHANNEL_STUB` | No | `false` | Run delivery simulation in-process (skips stub HTTP) |
| `CRM_RECEIPT_URL` | No | `http://127.0.0.1:$PORT/api/receipts` | Receipt callback URL (stub + embedded simulator) |
| `DATABASE_URL` | No | `sqlite:///./bare.db` | SQLite connection string |
| `PORT` | No | `8000` | HTTP port (Railway injects this; used for default receipt URL) |
| `OPENAI_BASE_URL` | No | auto-detected for `sk-or-*` keys | OpenAI-compatible API base URL |

On Windows, if `.env` is saved as `.env.txt`, the app loads that automatically.

### `channel-stub/.env`

| Variable | Required | Default | Description |
|---|---|---|---|
| `CRM_RECEIPT_URL` | No | `http://localhost:8000/api/receipts` | Where delivery receipts are posted |

## Campaign delivery flow

```
POST /api/campaigns/{id}/send
  → expand_and_dispatch (campaign_service)
      if EMBEDDED_CHANNEL_STUB=true → embedded simulator
      else POST channel-stub/send
           on failure → embedded simulator (auto-fallback)
  → receipts POST /api/receipts → message status updates
```

## Docker deployment

From the repository root:

```bash
echo "OPENAI_API_KEY=your-key-here" > .env
docker compose up --build -d
```

Services:

- CRM API: `http://localhost:8000`
- Channel stub: `http://localhost:8001`
- API docs: `http://localhost:8000/docs`

### Production notes

- Set `OPENAI_API_KEY` via your host's secret manager.
- **Railway (single service, root = `crm-backend`):** `channel-stub` is not deployed. The CRM auto-falls back to the embedded simulator when `CHANNEL_STUB_URL` is unreachable. Optionally set `EMBEDDED_CHANNEL_STUB=true` to skip stub HTTP entirely. Leave `CRM_RECEIPT_URL` **unset** so it defaults to `http://127.0.0.1:$PORT/api/receipts`.
- **Railway (two services):** Deploy `channel-stub` as a second service (root = `channel-stub`), set `CHANNEL_STUB_URL` on CRM to the stub's URL, and set `CRM_RECEIPT_URL` on the stub to the CRM's `/api/receipts` endpoint.
- Demo data is seeded automatically on first boot when the database is empty. Run `python seed/generate.py` only to **force a full reset** (destructive).
- SQLite is fine for demos; use a managed database for production workloads.

## API overview

| Endpoint group | Routes |
|---|---|
| Customers | `GET/POST /api/customers`, `GET /api/customers/{id}` |
| Orders | `POST /api/orders` |
| Segments | `GET/POST /api/segments`, `GET /api/segments/{id}`, `POST /api/segments/interpret`, `POST /api/segments/preview` |
| Campaigns | `GET/POST /api/campaigns`, `GET /api/campaigns/{id}`, `POST /api/campaigns/{id}/send`, `GET /api/campaigns/{id}/messages`, `GET /api/campaigns/stats` |
| AI co-pilot | `POST /api/copilot/chat` |
| Receipts | `POST /api/receipts` (channel-stub or embedded simulator) |

## Project structure

```
crm-backend/
├── main.py              # FastAPI app entrypoint + auto-seed on startup
├── config.py            # Environment configuration
├── db.py                # Database engine and session
├── schemas.py           # Pydantic request/response models
├── models/              # SQLModel table definitions
├── routes/              # API route handlers
├── services/
│   ├── campaign_service.py    # Send orchestration + stats
│   ├── channel_simulator.py   # Embedded delivery fallback
│   ├── message_service.py     # Receipt handling
│   ├── segment_service.py     # Filter evaluation
│   └── ai_service.py          # AI integration
└── seed/generate.py     # Synthetic data seeder (manual / destructive reset)

channel-stub/
├── main.py              # Stub API (POST /send)
└── simulator.py         # Async delivery lifecycle simulation
```
