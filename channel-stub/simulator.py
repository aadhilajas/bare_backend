"""
simulator.py — Async delivery lifecycle simulation for the Bare channel stub.

How it works
------------
1. POST /send calls simulate_delivery() as a FastAPI BackgroundTask.
2. simulate_delivery() walks through a fixed probability chain, sleeping
   between each event to create realistic timing.
3. Each event is posted to the CRM's receipt endpoint via post_receipt().
4. post_receipt() retries up to MAX_RETRIES times with exponential backoff
   if the CRM returns a 5xx or is unreachable.

Lifecycle probabilities (each is conditional on the previous step succeeding)
--------------
  sent       100 %   — every accepted message reaches "sent"
  delivered   85 %   — 15 % fail instead and stop here
  opened      55 %   — of those delivered
  read        40 %   — of those opened
  clicked     20 %   — of those read

Delays (seconds, chosen uniformly from the given range per event)
--------------
  initial jitter   0.0 – 1.0   so a large campaign doesn't arrive in one burst
  sent             0.5 – 1.5
  delivered        1.0 – 4.0
  opened           2.0 – 7.0
  read             1.0 – 3.0
  clicked          0.5 – 2.0

Full lifecycle timing for a single message is therefore 5 – 19 seconds,
which keeps the demo live and watchable without being instant or excessively slow.

Retry / backoff
---------------
  MAX_RETRIES = 3
  wait after attempt n = BACKOFF_BASE ** n   →   2s, 4s, 8s
  After all attempts fail the event is logged and silently dropped.
  The CRM message stays in its current state; no corrupt data is written.
"""

import asyncio
import random
from datetime import datetime, timezone

import httpx

from config import CRM_RECEIPT_URL

# ── Tunable constants ─────────────────────────────────────────────────────────

MAX_RETRIES: int = 3
BACKOFF_BASE: int = 2   # seconds; wait = BACKOFF_BASE ** attempt_number

FAILURE_REASONS: list[str] = [
    "DELIVERY_TIMEOUT",
    "INVALID_RECIPIENT",
    "USER_OPTED_OUT",
    "NETWORK_ERROR",
    "SPAM_FILTER",
]

# Each step: status, (delay_lo, delay_hi) seconds, probability of occurring
# given that the previous step occurred.
LIFECYCLE: list[dict] = [
    {"status": "sent",      "delay": (0.5, 1.5),  "probability": 1.00},
    {"status": "delivered", "delay": (1.0, 4.0),  "probability": 0.85},
    {"status": "opened",    "delay": (2.0, 7.0),  "probability": 0.55},
    {"status": "read",      "delay": (1.0, 3.0),  "probability": 0.40},
    {"status": "clicked",   "delay": (0.5, 2.0),  "probability": 0.20},
]


# ── Receipt posting ───────────────────────────────────────────────────────────

async def _post_receipt(receipt: dict, retries: int = MAX_RETRIES) -> None:
    """
    POST one receipt to the CRM receipt endpoint.
    Retries on 5xx or network failure with exponential backoff.
    2xx and 4xx responses are treated as final (the CRM either accepted or
    intentionally rejected the event — no point retrying a 422 or 409).
    """
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(CRM_RECEIPT_URL, json=receipt)

            if resp.status_code < 500:
                return  # success or client-side rejection — stop retrying

            print(
                f"[stub] receipt POST returned {resp.status_code} "
                f"(attempt {attempt + 1}/{retries})"
            )

        except Exception as exc:
            print(
                f"[stub] receipt POST error "
                f"(attempt {attempt + 1}/{retries}): {exc}"
            )

        if attempt < retries - 1:
            wait_seconds = BACKOFF_BASE ** (attempt + 1)
            await asyncio.sleep(wait_seconds)

    print(
        f"[stub] giving up after {retries} attempts "
        f"for message_id={receipt.get('message_id')}"
    )


def _make_receipt(payload: dict, status: str, failure_reason: str | None = None) -> dict:
    """Build a receipt dict aligned with the CRM's ReceiptPayload schema."""
    receipt: dict = {
        "message_id":  payload["message_id"],
        "campaign_id": payload["campaign_id"],
        "customer_id": payload["customer_id"],
        "status":      status,
        "event_time":  datetime.now(timezone.utc).isoformat(),
    }
    if failure_reason:
        receipt["failure_reason"] = failure_reason
    return receipt


# ── Simulation ────────────────────────────────────────────────────────────────

async def simulate_delivery(payload: dict) -> None:
    """
    Simulate the full delivery lifecycle for one message.
    Called as a background task from POST /send — runs concurrently with
    all other in-flight simulations via asyncio.

    payload fields expected: message_id, campaign_id, customer_id, channel,
                             recipient, message
    """
    # Small per-message initial jitter so a large campaign batch doesn't
    # hammer the CRM receipt endpoint in a single synchronous wave.
    await asyncio.sleep(random.uniform(0.0, 1.0))

    for step in LIFECYCLE:
        status: str = step["status"]
        delay_lo, delay_hi = step["delay"]
        probability: float = step["probability"]

        # Sleep before emitting — simulates network/delivery latency
        await asyncio.sleep(random.uniform(delay_lo, delay_hi))

        # Decide whether this step completes successfully
        if random.random() > probability:
            # The "delivered" step failing means the message was not delivered —
            # emit a "failed" event and stop the lifecycle for this message.
            # Any other step failing (opened, read, clicked) means the recipient
            # simply didn't engage further — no event is emitted, lifecycle ends.
            if status == "delivered":
                await _post_receipt(
                    _make_receipt(
                        payload,
                        status="failed",
                        failure_reason=random.choice(FAILURE_REASONS),
                    )
                )
            return  # stop progressing regardless of which step failed

        # Step succeeded — post the event to the CRM
        await _post_receipt(_make_receipt(payload, status=status))
