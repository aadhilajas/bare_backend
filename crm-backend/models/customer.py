import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint


class Customer(SQLModel, table=True):
    """
    Represents a shopper in the Bare skincare brand.

    Aggregate fields (total_orders, total_spend, last_order_date) are cached
    on this row and updated by the order service each time a new order is
    created. They exist for fast segmentation filtering without joining to
    the Order table every query.

    total_spend uses float (SQLite REAL). Adequate precision for demo amounts.
    tags stores a JSON array string e.g. '["oily-skin", "vip"]' — parsed
    by the service layer.
    """

    __tablename__ = "customer"
    __table_args__ = (UniqueConstraint("email", name="uq_customer_email"),)

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    name: str
    email: str = Field(index=True)
    phone: str
    city: str = Field(index=True)
    gender: str  # male | female | other
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Cached aggregates — maintained by order service, not computed at query time
    total_orders: int = Field(default=0)
    total_spend: float = Field(default=0.0)
    last_order_date: Optional[datetime] = Field(default=None)

    # JSON array string: '["oily-skin", "vip"]' — serialised/parsed by service layer
    tags: Optional[str] = Field(default=None)
