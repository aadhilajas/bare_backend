import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class Campaign(SQLModel, table=True):
    """
    Represents a planned or launched communication to a segment.

    channel values: whatsapp | sms | email | rcs
    status values:  draft | sending | sent

    message_template is the raw template text. Personalisation variables
    (e.g. {{name}}) are resolved per-customer by the campaign service when
    creating Message records.

    ai_reasoning stores the AI justification for the audience and message choice.
    sent_at is null until the campaign transitions out of draft.
    """

    __tablename__ = "campaign"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    name: str = Field(min_length=1)
    segment_id: str = Field(foreign_key="segment.id", index=True)
    channel: str  # whatsapp | sms | email | rcs
    message_template: str
    status: str = Field(default="draft")  # draft | sending | sent
    ai_reasoning: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = Field(default=None)
