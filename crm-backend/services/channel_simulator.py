"""
In-process delivery simulation for deployments where channel-stub is not running
(e.g. Railway with root directory = crm-backend only).

Mirrors channel-stub/simulator.py: same lifecycle probabilities and delays,
posting receipt callbacks to CRM_RECEIPT_URL (/api/receipts).
"""

import asyncio
import random
from datetime import datetime, timezone

import httpx

from config import CRM_RECEIPT_URL

MAX_RETRIES = 3
BACKOFF_BASE = 2

FAILURE_REASONS = [
    "DELIVERY_TIMEOUT",
    "INVALID_RECIPIENT",
    "USER_OPTED_OUT",
    "NETWORK_ERROR",
    "SPAM_FILTER",
]

LIFECYCLE = [
    {"status": "sent",      "delay": (0.5, 1.5),  "probability": 1.00},
    {"status": "delivered", "delay": (1.0, 4.0),  "probability": 0.85},
    {"status": "opened",    "delay": (2.0, 7.0),  "probability": 0.55},
    {"status": "read",      "delay": (1.0, 3.0),  "probability": 0.40},
    {"status": "clicked",   "delay": (0.5, 2.0),  "probability": 0.20},
]


def schedule_delivery_simulation(payload: dict, *, reason: str) -> None:
    """Fire-and-forget async simulation for one message."""
    message_id = payload.get("message_id", "?")
    print(
        f"[embedded-stub] message={message_id} scheduled reason={reason} "
        f"receipt_url={CRM_RECEIPT_URL}"
    )
    asyncio.create_task(simulate_delivery(payload))


async def _post_receipt(receipt: dict, retries: int = MAX_RETRIES) -> bool:
    message_id = receipt.get("message_id", "?")
    status = receipt.get("status", "?")
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(CRM_RECEIPT_URL, json=receipt)

            if resp.status_code < 500:
                print(
                    f"[embedded-stub] message={message_id} receipt status={status} "
                    f"posted successfully http={resp.status_code}"
                )
                return True

            print(
                f"[embedded-stub] message={message_id} receipt status={status} "
                f"POST returned {resp.status_code} (attempt {attempt + 1}/{retries})"
            )

        except Exception as exc:
            print(
                f"[embedded-stub] message={message_id} receipt status={status} "
                f"POST error (attempt {attempt + 1}/{retries}): {exc!r}"
            )

        if attempt < retries - 1:
            await asyncio.sleep(BACKOFF_BASE ** (attempt + 1))

    print(
        f"[embedded-stub] message={message_id} receipt status={status} "
        f"giving up after {retries} attempts"
    )
    return False


def _make_receipt(payload: dict, status: str, failure_reason: str | None = None) -> dict:
    receipt = {
        "message_id": payload["message_id"],
        "campaign_id": payload["campaign_id"],
        "customer_id": payload["customer_id"],
        "status": status,
        "event_time": datetime.now(timezone.utc).isoformat(),
    }
    if failure_reason:
        receipt["failure_reason"] = failure_reason
    return receipt


async def simulate_delivery(payload: dict) -> None:
    message_id = payload.get("message_id", "?")
    print(f"[embedded-stub] message={message_id} simulation started")
    await asyncio.sleep(random.uniform(0.0, 1.0))

    for step in LIFECYCLE:
        status = step["status"]
        delay_lo, delay_hi = step["delay"]
        probability = step["probability"]

        await asyncio.sleep(random.uniform(delay_lo, delay_hi))

        if random.random() > probability:
            if status == "delivered":
                await _post_receipt(
                    _make_receipt(
                        payload,
                        status="failed",
                        failure_reason=random.choice(FAILURE_REASONS),
                    )
                )
            print(f"[embedded-stub] message={message_id} simulation ended early at {status}")
            return

        await _post_receipt(_make_receipt(payload, status=status))

    print(f"[embedded-stub] message={message_id} simulation completed full lifecycle")
