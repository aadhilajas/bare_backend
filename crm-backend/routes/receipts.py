from fastapi import APIRouter, Depends

from db import get_session
from schemas import ReceiptPayload
from services.message_service import apply_receipt
from sqlmodel import Session

router = APIRouter(tags=["receipts"])


# ── POST /api/receipts ────────────────────────────────────────────────────────

@router.post("/receipts", status_code=200)
def receive_receipt(
    body: ReceiptPayload,
    session: Session = Depends(get_session),
) -> dict:
    """
    Ingest an async delivery callback from the channel stub.
    Idempotent: duplicate or retrograde events are silently accepted (200 OK)
    so the stub does not need to retry on already-processed receipts.
    """
    result = apply_receipt(
        session=session,
        payload={
            "message_id":     body.message_id,
            "status":         body.status,
            "event_time":     body.event_time,
            "failure_reason": body.failure_reason,
        },
    )
    return result
