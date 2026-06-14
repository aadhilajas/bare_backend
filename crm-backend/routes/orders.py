from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from db import get_session
from models.customer import Customer
from models.order import Order
from schemas import OrderCreate, OrderOut

router = APIRouter(tags=["orders"])


# ── POST /api/orders ──────────────────────────────────────────────────────────

@router.post("/orders", status_code=201, response_model=OrderOut)
def create_order(
    body: OrderCreate,
    session: Session = Depends(get_session),
) -> OrderOut:
    customer = session.get(Customer, body.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    order = Order(
        customer_id=body.customer_id,
        amount=body.amount,
        product_category=body.product_category,
        status=body.status,
        created_at=body.created_at or datetime.now(timezone.utc),
    )
    session.add(order)

    # Update cached aggregate fields on the Customer row
    customer.total_orders += 1
    customer.total_spend = round(customer.total_spend + body.amount, 2)
    # Normalise to naive UTC for comparison — SQLite returns naive datetimes
    # and Python raises TypeError when comparing aware with naive.
    order_dt = order.created_at.replace(tzinfo=None) if order.created_at.tzinfo else order.created_at
    last_dt  = customer.last_order_date.replace(tzinfo=None) if (
        customer.last_order_date is not None and customer.last_order_date.tzinfo
    ) else customer.last_order_date

    if last_dt is None or order_dt > last_dt:
        customer.last_order_date = order.created_at

    session.add(customer)
    session.commit()
    session.refresh(order)

    return OrderOut.model_validate(order)
