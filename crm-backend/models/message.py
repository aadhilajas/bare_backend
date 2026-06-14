import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Message(SQLModel, table=True):
    """
    Represents one message sent to one customer as part of a campaign.

    Status lifecycle (monotonic — never downgraded):
        queued → sent → delivered → opened → read → clicked
        queued → sent → failed  (terminal)

    Each status transition stamps the corresponding *_at timestamp.
    failed_reason captures the error string from the channel stub callback.

    status is indexed to make campaign stats aggregations (COUNT GROUP BY
    status) efficient without scanning personalised_text.
    """

    __tablename__ = "message"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    customer_id: str = Field(foreign_key="customer.id", index=True)
    channel: str
    personalised_text: str
    status: str = Field(default="queued", index=True)
    # queued | sent | delivered | opened | read | clicked | failed

    sent_at: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(default=None)
    opened_at: Optional[datetime] = Field(default=None)
    read_at: Optional[datetime] = Field(default=None)
    clicked_at: Optional[datetime] = Field(default=None)
    failed_reason: Optional[str] = Field(default=None)
