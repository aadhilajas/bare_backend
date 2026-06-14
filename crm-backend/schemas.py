"""
Pydantic request and response schemas for the Bare CRM API.

Kept separate from SQLModel table classes so route handlers stay thin
and so the API surface can evolve independently of the DB schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, model_validator


# ── Shared ────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    """Base with from_attributes=True so SQLModel rows can be validated directly."""
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _attach_utc_to_naive_datetimes(self) -> OrmBase:
        """
        SQLite stores datetimes as plain strings and returns them as naive
        Python datetime objects (no tzinfo).  All our stored datetimes are
        UTC, so we attach UTC here — after the ORM object has been read —
        so that FastAPI serialises them as "…+00:00" rather than bare ISO
        strings that browsers misinterpret as local time.
        """
        for field_name in self.model_fields:
            v = getattr(self, field_name, None)
            if isinstance(v, datetime) and v.tzinfo is None:
                setattr(self, field_name, v.replace(tzinfo=timezone.utc))
        return self


# ── Customers ─────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    email: str
    phone: str
    city: str
    gender: str
    tags: Optional[list[str]] = None


class CustomerOut(OrmBase):
    id: str
    name: str
    email: str
    phone: str
    city: str
    gender: str
    created_at: datetime
    total_orders: int
    total_spend: float
    last_order_date: Optional[datetime] = None
    tags: Optional[str] = None  # stored as JSON string


class OrderOut(OrmBase):
    id: str
    customer_id: str
    amount: float
    product_category: str
    status: str
    created_at: datetime


class CustomerDetailOut(CustomerOut):
    orders: list[OrderOut] = []


class CustomerListResponse(BaseModel):
    customers: list[CustomerOut]
    total: int
    page: int
    limit: int


# ── Orders ────────────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    customer_id: str
    amount: float
    product_category: str
    status: str = "completed"
    created_at: Optional[datetime] = None


# ── Segments ──────────────────────────────────────────────────────────────────

class FilterCondition(BaseModel):
    field: str
    operator: str
    value: Any  # int, float, or str depending on field


class SegmentCreate(BaseModel):
    name: str
    description: str = ""
    filters: list[FilterCondition]
    match_mode: str = "ALL"
    ai_reasoning: Optional[str] = None


class SegmentOut(OrmBase):
    id: str
    name: str
    description: str
    filters: str          # JSON string as stored
    match_mode: str
    customer_count: int
    ai_reasoning: Optional[str] = None
    created_at: datetime


class SegmentInterpretRequest(BaseModel):
    intent_text: str
    context: Optional[dict] = None


class SegmentInterpretResponse(BaseModel):
    name: str
    filters: list[FilterCondition]
    match_mode: str
    explanation: str


class SegmentPreviewRequest(BaseModel):
    filters: list[FilterCondition]
    match_mode: str = "ALL"


class SegmentPreviewCustomer(OrmBase):
    id: str
    name: str
    city: str
    total_spend: float
    total_orders: int


class SegmentPreviewResponse(BaseModel):
    count: int
    customers: list[SegmentPreviewCustomer]


# ── Campaigns ─────────────────────────────────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str
    segment_id: str
    channel: str          # whatsapp | sms | email | rcs
    message_template: str
    ai_reasoning: Optional[str] = None


class CampaignOut(OrmBase):
    id: str
    name: str
    segment_id: str
    channel: str
    message_template: str
    status: str
    ai_reasoning: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class CampaignStats(BaseModel):
    total_sent: int
    delivered: int
    failed: int
    opened: int
    read: int
    clicked: int
    delivery_rate: float  # percentage
    open_rate: float
    click_rate: float


class CampaignDetailOut(CampaignOut):
    stats: CampaignStats


class ChannelStats(BaseModel):
    """Delivery metrics for a single channel, aggregated across all campaigns."""
    channel: str
    campaigns: int
    total_sent: int
    delivery_rate: float
    open_rate: float
    click_rate: float


class AggregateStats(BaseModel):
    """Cross-campaign delivery rollup returned by GET /api/campaigns/stats."""
    total_sent: int
    delivered: int
    opened: int
    read: int
    clicked: int
    failed: int
    delivery_rate: float
    open_rate: float
    click_rate: float
    by_channel: list[ChannelStats]


class MessageOut(OrmBase):
    """Per-message view used by GET /api/campaigns/{id}/messages.
    Inherits OrmBase so all datetime fields get UTC attached before
    serialisation — the SQLModel Message table class does not inherit OrmBase
    and would emit naive datetime strings without this wrapper.
    """
    id: str
    campaign_id: str
    customer_id: str
    channel: str
    personalised_text: str
    status: str
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    failed_reason: Optional[str] = None


# ── Co-pilot ──────────────────────────────────────────────────────────────────

class CopilotChatRequest(BaseModel):
    message: str
    current_page: str
    data_context: dict = {}
    user_action: Optional[str] = None
    # Previous turns in the session — list of {"role": "user"|"assistant", "content": str}.
    # The frontend trims this to the last MAX_HISTORY messages before sending.
    history: list[dict] = []


class CopilotChatResponse(BaseModel):
    assistant_text: str
    suggestions: Optional[dict] = None


# ── Receipts ──────────────────────────────────────────────────────────────────

class ReceiptPayload(BaseModel):
    message_id: str
    campaign_id: str
    customer_id: str
    status: str
    event_time: datetime
    failure_reason: Optional[str] = None
    metadata: Optional[dict] = None
