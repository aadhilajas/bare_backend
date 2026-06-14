import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class Segment(SQLModel, table=True):
    """
    Represents a saved audience definition.

    filters stores the conditions list as a JSON string:
        '[{"field": "city", "operator": "equals", "value": "Mumbai"}, ...]'

    match_mode is the authoritative ALL/ANY flag and is kept as a separate
    column for fast reading. The segment_service composes match_mode + filters
    when evaluating the audience.

    customer_count is cached on create and refreshed when a segment is fetched
    via GET /api/segments/{id}.

    ai_reasoning stores the AI explanation for why this audience is valuable.
    """

    __tablename__ = "segment"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    name: str = Field(min_length=1)
    description: str = Field(default="")
    filters: str = Field(default="[]")   # JSON string — conditions array
    match_mode: str = Field(default="ALL")  # ALL | ANY
    customer_count: int = Field(default=0)  # Cached; recomputed on save
    ai_reasoning: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
