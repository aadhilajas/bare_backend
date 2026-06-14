# Bare CRM — Backend

FastAPI backend for **Bare**, an AI-native mini CRM for a fictional skincare D2C brand. This repository contains the CRM API and the channel-stub service that simulates message delivery.

> **Repository note:** This is the **backend** repo. The React frontend lives in a separate repository. Push only the contents listed under [Repository contents](#repository-contents).

## Stack

| Component | Technology |
|---|---|
| CRM API | FastAPI + SQLModel + SQLite |
| Channel stub | FastAPI (separate service on port 8001) |
| AI | OpenAI-compatible API (`gpt-4o-mini`, supports OpenRouter) |

## Services

| Service | Port | Purpose |
|---|---|---|
| `crm-backend` | 8000 | CRM API — customers, segments, campaigns, analytics, AI co-pilot |
| `channel-stub` | 8001 | Simulates WhatsApp/SMS/email delivery and posts receipts back to the CRM |

## Repository contents

Push these paths as the **root** of this GitHub repository:

```
bare-backend/
├── crm-backend/       # CRM API service
├── channel-stub/      # Delivery simulation service
├── docker-compose.yml
├── .gitignore
└── README.md
```

Do **not** include `docs/`, `frontend/`, `.cursorrules`, or any local `.env` files.

## Prerequisites

- Python 3.11+
- pip
- Docker & Docker Compose (optional, for containerised run)

## Local setup (without Docker)

### 1. CRM backend

```bash
cd crm-backend
pip install -r requirements.txt
cp .env.example .env          # then add your OPENAI_API_KEY
python seed/generate.py       # seed 200 customers, orders, and 5 segments
python -m uvicorn main:app --reload --port 8000
```

### 2. Channel stub (separate terminal)

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
| `CRM_RECEIPT_URL` | No | `http://localhost:8000/api/receipts` | Receipt callback URL |
| `DATABASE_URL` | No | `sqlite:///./bare.db` | SQLite connection string |
| `OPENAI_BASE_URL` | No | auto-detected for `sk-or-*` keys | OpenAI-compatible API base URL |

### `channel-stub/.env`

| Variable | Required | Default | Description |
|---|---|---|---|
| `CRM_RECEIPT_URL` | No | `http://localhost:8000/api/receipts` | Where delivery receipts are posted |

## Docker deployment

From the repository root:

```bash
# Create env file for compose (do not commit this file)
echo "OPENAI_API_KEY=your-key-here" > .env

docker compose up --build -d
```

Services will be available at:

- CRM API: `http://localhost:8000`
- Channel stub: `http://localhost:8001`
- API docs: `http://localhost:8000/docs`

### Production notes

- Set `OPENAI_API_KEY` via your host's secret manager or a `.env` file excluded from git.
- For cloud deployment, update `CHANNEL_STUB_URL` and `CRM_RECEIPT_URL` to use internal service hostnames.
- SQLite is fine for demos; use a managed database for production workloads.
- Run `python seed/generate.py` inside the CRM container once after first deploy if you need demo data.

## API overview

| Endpoint group | Base path |
|---|---|
| Customers | `GET/POST /api/customers` |
| Segments | `GET/POST /api/segments`, `POST /api/segments/interpret`, `POST /api/segments/preview` |
| Campaigns | `GET/POST /api/campaigns`, `POST /api/campaigns/{id}/send`, `GET /api/campaigns/stats` |
| AI co-pilot | `POST /api/copilot/chat` |
| Receipts | `POST /api/receipts` (called by channel-stub only) |

## Project structure

```
crm-backend/
├── main.py              # FastAPI app entrypoint
├── config.py            # Environment configuration
├── db.py                # Database engine and session
├── schemas.py           # Pydantic request/response models
├── models/              # SQLModel table definitions
├── routes/              # API route handlers
├── services/            # Business logic and AI integration
└── seed/generate.py     # Synthetic data seeder

channel-stub/
├── main.py              # Stub API (POST /send)
└── simulator.py         # Async delivery lifecycle simulation
```

## Pushing to GitHub

```bash
# From your machine, initialise the backend repo
git init
git add crm-backend/ channel-stub/ docker-compose.yml .gitignore README.md
git commit -m "Initial backend submission"
git remote add origin https://github.com/<you>/bare-backend.git
git push -u origin main
```
