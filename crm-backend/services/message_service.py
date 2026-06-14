"""
Message service — receipt handling, idempotency, monotonic status progression.

Rules
-----
1. Use message_id as the idempotency key.
2. Status transitions are monotonic: an incoming status must rank higher
   than the current status before it is applied.
3. "failed" is a terminal state that can be reached from any non-failed state.
4. Duplicate or out-of-order callbacks are silently ignored (not an error).
5. Each transition stamps the corresponding *_at timestamp field.
"""

from datetime import datetime, timezone
from sqlmodel import Session

from models.message import Message

# Ascending rank — higher number = more advanced state.
# "failed" sits at -1 so it is handled via a separate branch, not rank comparison.
STATUS_RANK: dict[str, int] = {
    "queued":    0,
    "sent":      1,
    "delivered": 2,
    "opened":    3,
    "read":      4,
    "clicked":   5,
}

# Maps a status value to the timestamp column it should stamp on transition.
TIMESTAMP_FIELD: dict[str, str] = {
    "sent":      "sent_at",
    "delivered": "delivered_at",
    "opened":    "opened_at",
    "read":      "read_at",
    "clicked":   "clicked_at",
}


def is_advancement(current_status: str, incoming_status: str) -> bool:
    """
    Return True when the incoming status should be applied.

    "failed" advances from any non-failed state.
    Any other status advances only if its rank is strictly higher.
    """
    if incoming_status == "failed":
        return current_status != "failed"

    current_rank = STATUS_RANK.get(current_status, -1)
    incoming_rank = STATUS_RANK.get(incoming_status, -1)
    return incoming_rank > current_rank


def apply_receipt(session: Session, payload: dict) -> dict:
    """
    Apply a single callback receipt to its Message row.

    Returns a result dict:
      {"ok": True}                          — state was advanced
      {"ok": True, "skipped": True}         — duplicate or out-of-order, no change
      {"ok": False, "reason": "..."}        — message_id not found
    """
    message_id: str = payload["message_id"]
    incoming_status: str = payload["status"]
    event_time: datetime = payload.get("event_time") or datetime.now(timezone.utc)
    failure_reason: str | None = payload.get("failure_reason")

    msg: Message | None = session.get(Message, message_id)
    if msg is None:
        return {"ok": False, "reason": "message_not_found"}

    if not is_advancement(msg.status, incoming_status):
        # Duplicate or retrograde callback — safe to ignore
        return {"ok": True, "skipped": True}

    msg.status = incoming_status

    if incoming_status == "failed":
        msg.failed_reason = failure_reason or "unknown"
    else:
        ts_field = TIMESTAMP_FIELD.get(incoming_status)
        if ts_field:
            setattr(msg, ts_field, event_time)

    session.add(msg)
    session.commit()
    return {"ok": True}
