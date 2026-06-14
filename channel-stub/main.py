"""
Bare Channel Stub — FastAPI app.

Endpoints
---------
POST /send    Accept a message send request and schedule async delivery simulation.
GET  /health  Service liveness check.

This service has no database. It holds no business state between requests.
All simulation state lives transiently in asyncio coroutines while they run.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

from simulator import simulate_delivery


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Bare Channel Stub",
    version="0.1.0",
    description="Stubbed messaging channel for the Bare CRM demo.",
    lifespan=lifespan,
)


class SendPayload(BaseModel):
    message_id:  str
    campaign_id: str
    customer_id: str
    channel:     str   # whatsapp | sms | email | rcs
    recipient:   str   # phone or email
    message:     str


# ── POST /send ────────────────────────────────────────────────────────────────

@app.post("/send", status_code=202)
async def send_message(
    payload: SendPayload,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Accept a single message send request from the CRM.
    Immediately returns 202 Accepted and schedules async delivery simulation.
    The simulation posts receipt callbacks back to the CRM asynchronously.
    """
    background_tasks.add_task(simulate_delivery, payload.model_dump())
    return {"accepted": True, "message_id": payload.message_id}


# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "channel-stub"}
