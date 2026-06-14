"""
Campaign service — segment expansion, message creation, channel stub dispatch,
and campaign statistics computation.

Send flow
---------
1. Route handler sets campaign.status = "sending" and returns immediately.
2. expand_and_dispatch runs as a FastAPI BackgroundTask with its own DB session.
3. It resolves the segment audience, creates per-customer Message rows, then
   posts each message payload to the channel stub's POST /send endpoint.
4. On completion it marks the campaign as "sent".

If the channel stub is unreachable, an embedded in-process simulator runs instead
(see channel_simulator.py). The campaign still moves to "sent" either way.

Stats
-----
Campaign stats are derived from Message rows on every request, never stored.
"""

import httpx
from datetime import datetime, timezone
from sqlmodel import Session, select

from config import CHANNEL_STUB_URL, EMBEDDED_CHANNEL_STUB
from db import engine
from models.campaign import Campaign
from models.customer import Customer
from models.message import Message
from models.segment import Segment
from schemas import CampaignStats
from services.segment_service import evaluate_filters
from services.channel_simulator import schedule_delivery_simulation


# ── Personalisation ───────────────────────────────────────────────────────────

def _personalise(template: str, customer: Customer) -> str:
    """
    Substitute simple template variables in a message template.
    Supported tokens: {{name}}, {{first_name}}, {{city}}.
    """
    first_name = customer.name.split()[0]
    return (
        template
        .replace("{{name}}", customer.name)
        .replace("{{first_name}}", first_name)
        .replace("{{city}}", customer.city)
    )


def _recipient(customer: Customer, channel: str) -> str:
    """Return the appropriate contact identifier for the given channel."""
    if channel in ("whatsapp", "sms"):
        return customer.phone
    return customer.email  # email, rcs


# ── Stats ─────────────────────────────────────────────────────────────────────

def compute_campaign_stats(session: Session, campaign_id: str) -> CampaignStats:
    """
    Derive campaign delivery metrics from the current Message row statuses.
    Stats are cumulative: a "clicked" message also counts toward opened/read.
    """
    messages = list(
        session.exec(select(Message).where(Message.campaign_id == campaign_id)).all()
    )

    if not messages:
        return CampaignStats(
            total_sent=0, delivered=0, failed=0,
            opened=0, read=0, clicked=0,
            delivery_rate=0.0, open_rate=0.0, click_rate=0.0,
        )

    # All statuses that indicate the message left the queued state and was
    # dispatched to the channel stub (including failed ones — they were sent
    # but not delivered, so they must count in the denominator).
    dispatched = {"sent", "delivered", "opened", "read", "clicked", "failed"}

    total_sent = sum(1 for m in messages if m.status in dispatched)
    delivered  = sum(1 for m in messages if m.status in {"delivered", "opened", "read", "clicked"})
    opened     = sum(1 for m in messages if m.status in {"opened", "read", "clicked"})
    read_count = sum(1 for m in messages if m.status in {"read", "clicked"})
    clicked    = sum(1 for m in messages if m.status == "clicked")
    failed     = sum(1 for m in messages if m.status == "failed")

    # Avoid division by zero for draft campaigns with no messages yet
    base = total_sent if total_sent > 0 else 1

    return CampaignStats(
        total_sent=total_sent,
        delivered=delivered,
        failed=failed,
        opened=opened,
        read=read_count,
        clicked=clicked,
        delivery_rate=round(delivered / base * 100, 1),
        open_rate=round(opened / base * 100, 1),
        click_rate=round(clicked / base * 100, 1),
    )


# ── Send orchestration ────────────────────────────────────────────────────────

async def expand_and_dispatch(campaign_id: str) -> None:
    """
    Background task: expand segment audience → create Message rows →
    dispatch to channel stub → mark campaign sent.

    Opens its own DB session because this runs after the request session closes.
    """
    with Session(engine) as session:
        campaign: Campaign | None = session.get(Campaign, campaign_id)
        if not campaign:
            return

        segment: Segment | None = session.get(Segment, campaign.segment_id)
        if not segment:
            return

        customers = evaluate_filters(session, segment.filters, segment.match_mode)

        # Index customers by ID for O(1) lookup during dispatch
        customer_map: dict[str, Customer] = {c.id: c for c in customers}

        # Create Message rows for every customer in the audience
        messages: list[Message] = [
            Message(
                campaign_id=campaign_id,
                customer_id=customer.id,
                channel=campaign.channel,
                personalised_text=_personalise(campaign.message_template, customer),
                status="queued",
            )
            for customer in customers
        ]

        session.add_all(messages)
        session.commit()

        # IDs are generated by uuid4() before commit — no refresh loop needed.

        print(
            f"[dispatch] campaign={campaign_id} messages={len(messages)} "
            f"EMBEDDED_CHANNEL_STUB={EMBEDDED_CHANNEL_STUB} "
            f"CHANNEL_STUB_URL={CHANNEL_STUB_URL}"
        )

        # Dispatch each message to the channel stub (or run embedded simulation)
        async with httpx.AsyncClient(timeout=10.0) as client:
            for msg in messages:
                customer = customer_map.get(msg.customer_id)
                if not customer:
                    continue
                payload = {
                    "message_id": msg.id,
                    "campaign_id": campaign_id,
                    "customer_id": customer.id,
                    "channel": campaign.channel,
                    "recipient": _recipient(customer, campaign.channel),
                    "message": msg.personalised_text,
                }
                if EMBEDDED_CHANNEL_STUB:
                    print(
                        f"[dispatch] message={msg.id} path=embedded "
                        f"(EMBEDDED_CHANNEL_STUB=true, skipping stub HTTP)"
                    )
                    schedule_delivery_simulation(payload, reason="embedded_flag")
                    continue
                stub_url = f"{CHANNEL_STUB_URL}/send"
                print(f"[dispatch] message={msg.id} attempting stub HTTP POST {stub_url}")
                try:
                    resp = await client.post(stub_url, json=payload)
                    resp.raise_for_status()
                    print(
                        f"[dispatch] message={msg.id} stub HTTP succeeded "
                        f"status={resp.status_code}"
                    )
                except Exception as exc:
                    print(
                        f"[dispatch] message={msg.id} stub HTTP failed: {exc!r} "
                        f"— entering embedded simulator"
                    )
                    schedule_delivery_simulation(payload, reason="stub_unreachable")

        # Mark campaign as sent regardless of stub reachability
        campaign.status = "sent"
        campaign.sent_at = datetime.now(timezone.utc)
        session.add(campaign)
        session.commit()
