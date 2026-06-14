from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from db import get_session
from models.campaign import Campaign
from models.message import Message
from models.segment import Segment
from schemas import (
    AggregateStats,
    ChannelStats,
    CampaignCreate,
    CampaignDetailOut,
    CampaignOut,
    CampaignStats,
    MessageOut,
)
from services.campaign_service import compute_campaign_stats, expand_and_dispatch

router = APIRouter(tags=["campaigns"])


# ── GET /api/campaigns ────────────────────────────────────────────────────────

@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(session: Session = Depends(get_session)) -> list[CampaignOut]:
    campaigns = session.exec(
        select(Campaign).order_by(Campaign.created_at.desc())
    ).all()
    return [CampaignOut.model_validate(c) for c in campaigns]


# ── GET /api/campaigns/stats ──────────────────────────────────────────────────
# Must be registered BEFORE /{campaign_id} so the literal path wins.

@router.get("/campaigns/stats", response_model=AggregateStats)
def aggregate_campaign_stats(
    session: Session = Depends(get_session),
) -> AggregateStats:
    """
    Cross-campaign delivery rollup: one DB scan over Message rows
    grouped by channel.  Used by the Analytics page.
    """
    messages = list(session.exec(select(Message)).all())
    campaigns = list(session.exec(select(Campaign)).all())

    # All statuses that indicate the message was dispatched (including failed —
    # they count toward the denominator for delivery rate).
    dispatched = {"sent", "delivered", "opened", "read", "clicked", "failed"}

    total_sent = sum(1 for m in messages if m.status in dispatched)
    delivered  = sum(1 for m in messages if m.status in {"delivered", "opened", "read", "clicked"})
    opened     = sum(1 for m in messages if m.status in {"opened", "read", "clicked"})
    read_count = sum(1 for m in messages if m.status in {"read", "clicked"})
    clicked    = sum(1 for m in messages if m.status == "clicked")
    failed     = sum(1 for m in messages if m.status == "failed")

    base = total_sent or 1

    # Per-channel breakdown — map campaign_id → channel once, then group messages
    campaign_channel: dict[str, str] = {c.id: c.channel for c in campaigns}
    campaign_count_by_channel: dict[str, int] = {}
    for c in campaigns:
        campaign_count_by_channel[c.channel] = campaign_count_by_channel.get(c.channel, 0) + 1

    channel_msgs: dict[str, list] = {}
    for m in messages:
        ch = campaign_channel.get(m.campaign_id, "unknown")
        channel_msgs.setdefault(ch, []).append(m)

    by_channel: list[ChannelStats] = []
    for ch, msgs in sorted(channel_msgs.items(), key=lambda kv: -len(kv[1])):
        ch_sent      = sum(1 for m in msgs if m.status in dispatched)
        ch_delivered = sum(1 for m in msgs if m.status in {"delivered", "opened", "read", "clicked"})
        ch_opened    = sum(1 for m in msgs if m.status in {"opened", "read", "clicked"})
        ch_clicked   = sum(1 for m in msgs if m.status == "clicked")
        ch_base      = ch_sent or 1
        by_channel.append(ChannelStats(
            channel=ch,
            campaigns=campaign_count_by_channel.get(ch, 0),
            total_sent=ch_sent,
            delivery_rate=round(ch_delivered / ch_base * 100, 1),
            open_rate=round(ch_opened / ch_base * 100, 1),
            click_rate=round(ch_clicked / ch_base * 100, 1),
        ))

    return AggregateStats(
        total_sent=total_sent,
        delivered=delivered,
        opened=opened,
        read=read_count,
        clicked=clicked,
        failed=failed,
        delivery_rate=round(delivered / base * 100, 1),
        open_rate=round(opened / base * 100, 1),
        click_rate=round(clicked / base * 100, 1),
        by_channel=by_channel,
    )


# ── GET /api/campaigns/{id} ───────────────────────────────────────────────────

@router.get("/campaigns/{campaign_id}", response_model=CampaignDetailOut)
def get_campaign(
    campaign_id: str,
    session: Session = Depends(get_session),
) -> CampaignDetailOut:
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    stats: CampaignStats = compute_campaign_stats(session, campaign_id)

    return CampaignDetailOut(
        **CampaignOut.model_validate(campaign).model_dump(),
        stats=stats,
    )


# ── POST /api/campaigns ───────────────────────────────────────────────────────

@router.post("/campaigns", status_code=201, response_model=CampaignOut)
def create_campaign(
    body: CampaignCreate,
    session: Session = Depends(get_session),
) -> CampaignOut:
    # Validate the segment exists
    if not session.get(Segment, body.segment_id):
        raise HTTPException(status_code=404, detail="Segment not found")

    campaign = Campaign(
        name=body.name,
        segment_id=body.segment_id,
        channel=body.channel,
        message_template=body.message_template,
        ai_reasoning=body.ai_reasoning,
        status="draft",
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    return CampaignOut.model_validate(campaign)


# ── POST /api/campaigns/{id}/send ─────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/send", response_model=CampaignOut)
def send_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> CampaignOut:
    campaign = session.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Campaign is already '{campaign.status}' and cannot be re-sent",
        )

    # Transition to "sending" immediately so the UI reflects activity
    campaign.status = "sending"
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    # Segment expansion + stub dispatch runs in the background
    background_tasks.add_task(expand_and_dispatch, campaign_id)

    return CampaignOut.model_validate(campaign)


# ── GET /api/campaigns/{id}/messages ─────────────────────────────────────────

@router.get("/campaigns/{campaign_id}/messages", response_model=list[MessageOut])
def list_campaign_messages(
    campaign_id: str,
    session: Session = Depends(get_session),
) -> list[MessageOut]:
    if not session.get(Campaign, campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    return list(
        session.exec(
            select(Message)
            .where(Message.campaign_id == campaign_id)
            .order_by(Message.status)
        ).all()
    )
