import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class Order(SQLModel, table=True):
    """
    Represents one purchase by a customer.

    status values: completed | returned | cancelled
    product_category is a free-text field (e.g. moisturiser, serum, spf,
    cleanser, toner) used in segment filter conditions.

    created_at is indexed to support date-range filter queries in the
    segment evaluator without a full table scan.
    """

    __tablename__ = "order"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    customer_id: str = Field(foreign_key="customer.id", index=True)
    amount: float  # SQLite REAL — adequate for demo monetary amounts
    product_category: str = Field(index=True)
    status: str = Field(default="completed")  # completed | returned | cancelled
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
