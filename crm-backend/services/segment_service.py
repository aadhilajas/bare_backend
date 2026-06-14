"""
Segment service — filter evaluation and customer count computation.

Builds dynamic SQLAlchemy WHERE clauses from the segment's JSON filter list
and evaluates them against the Customer (and Order) tables.

Supported fields
----------------
Customer-table direct:  last_order_date, total_spend, total_orders, city, gender
Order-table (subquery): product_category

Supported operators
-------------------
equals, greater_than, greater_than_or_equal, less_than, less_than_or_equal,
more_than_days_ago, less_than_days_ago
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_
from sqlmodel import Session, select

from models.customer import Customer
from models.order import Order


# Fields that live directly on the Customer table
_CUSTOMER_FIELDS = frozenset(
    ["last_order_date", "total_spend", "total_orders", "city", "gender"]
)


def _build_condition(cond: dict) -> Any:
    """
    Convert a single filter condition dict into a SQLAlchemy column expression.
    Raises ValueError for unknown fields or operators so callers can return 400.
    """
    field: str = cond["field"]
    op: str = cond["operator"]
    value = cond["value"]
    # Use datetime.now(timezone.utc).replace(tzinfo=None) — produces the same
    # naive-UTC value as the deprecated datetime.utcnow(), but avoids the
    # deprecation warning while keeping SQLite string comparisons correct.
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # product_category requires a subquery into the Order table
    if field == "product_category":
        if op != "equals":
            raise ValueError(f"product_category only supports 'equals', got '{op}'")
        subq = select(Order.customer_id).where(Order.product_category == value)
        return Customer.id.in_(subq)

    if field not in _CUSTOMER_FIELDS:
        raise ValueError(f"Unsupported filter field: '{field}'")

    col = getattr(Customer, field)

    if op == "equals":
        return col == value
    elif op == "greater_than":
        return col > value
    elif op == "greater_than_or_equal":
        return col >= value
    elif op == "less_than":
        return col < value
    elif op == "less_than_or_equal":
        return col <= value
    elif op == "more_than_days_ago":
        # e.g. last_order_date more_than_days_ago 90  →  col < (now - 90d)
        threshold = now - timedelta(days=int(value))
        return col < threshold
    elif op == "less_than_days_ago":
        # e.g. last_order_date less_than_days_ago 30  →  col >= (now - 30d)
        threshold = now - timedelta(days=int(value))
        return col >= threshold
    else:
        raise ValueError(f"Unsupported operator: '{op}'")


def evaluate_filters(
    session: Session, filters_json: str, match_mode: str
) -> list[Customer]:
    """
    Evaluate a segment's filter JSON against the database and return
    the list of matching Customer rows.

    filters_json: JSON string — array of {field, operator, value} dicts
    match_mode:   "ALL" (AND) or "ANY" (OR)
    """
    conditions_data: list[dict] = json.loads(filters_json or "[]")

    if not conditions_data:
        return list(session.exec(select(Customer)).all())

    conditions = [_build_condition(c) for c in conditions_data]

    if match_mode == "ALL":
        where_clause = and_(*conditions)
    else:
        where_clause = or_(*conditions)

    return list(session.exec(select(Customer).where(where_clause)).all())


def compute_customer_count(
    session: Session, filters_json: str, match_mode: str
) -> int:
    return len(evaluate_filters(session, filters_json, match_mode))
