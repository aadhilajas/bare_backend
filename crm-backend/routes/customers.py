import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlmodel import Session, select

from db import get_session
from models.customer import Customer
from models.order import Order
from schemas import (
    CustomerCreate,
    CustomerDetailOut,
    CustomerListResponse,
    CustomerOut,
    OrderOut,
)

router = APIRouter(tags=["customers"])


# ── GET /api/customers ────────────────────────────────────────────────────────

@router.get("/customers", response_model=CustomerListResponse)
def list_customers(
    session: Session = Depends(get_session),
    search: str | None = None,
    city: str | None = None,
    gender: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> CustomerListResponse:
    conditions = []

    if search:
        conditions.append(
            or_(
                Customer.name.ilike(f"%{search}%"),
                Customer.email.ilike(f"%{search}%"),
            )
        )
    if city:
        conditions.append(Customer.city == city)
    if gender:
        conditions.append(Customer.gender == gender)

    # Total count (no pagination)
    count_stmt = select(func.count(Customer.id))
    for c in conditions:
        count_stmt = count_stmt.where(c)
    total: int = session.exec(count_stmt).one()

    # Paginated data — order by most recently created
    data_stmt = (
        select(Customer)
        .order_by(Customer.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    for c in conditions:
        data_stmt = data_stmt.where(c)

    customers = session.exec(data_stmt).all()

    return CustomerListResponse(
        customers=[CustomerOut.model_validate(c) for c in customers],
        total=total,
        page=page,
        limit=limit,
    )


# ── GET /api/customers/{id} ───────────────────────────────────────────────────

@router.get("/customers/{customer_id}", response_model=CustomerDetailOut)
def get_customer(
    customer_id: str,
    session: Session = Depends(get_session),
) -> CustomerDetailOut:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
    ).all()

    return CustomerDetailOut(
        **CustomerOut.model_validate(customer).model_dump(),
        orders=[OrderOut.model_validate(o) for o in orders],
    )


# ── POST /api/customers ───────────────────────────────────────────────────────

@router.post("/customers", status_code=201, response_model=CustomerOut)
def create_customer(
    body: CustomerCreate,
    session: Session = Depends(get_session),
) -> CustomerOut:
    # Check email uniqueness before insert to return a clear 409
    existing = session.exec(
        select(Customer).where(Customer.email == body.email)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    tags_json = json.dumps(body.tags) if body.tags else None

    customer = Customer(
        name=body.name,
        email=body.email,
        phone=body.phone,
        city=body.city,
        gender=body.gender,
        created_at=datetime.now(timezone.utc),
        tags=tags_json,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    return CustomerOut.model_validate(customer)
