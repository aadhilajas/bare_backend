"""
Bare CRM — Seed Script
======================
Generates ~200 customers, ~750 orders, and 5 pre-built demo segments.

Run from /crm-backend:
    python seed/generate.py

The script is idempotent: it clears all existing data (customers, orders,
segments, campaigns, messages) before re-seeding.

Random seed is fixed at 42 so re-runs produce the same dataset.

Cohorts
-------
A  Loyal Repeat Buyers      40 customers   5–10 orders each   recent activity
B  Lapsed High-Value        50 customers   3–6 orders each    last order > 90 days ago
C  Recent First-Timers      40 customers   1–2 orders each    joined in last 60 days
D  Serum Enthusiasts        30 customers   3–6 orders each    ≥ 70 % serum orders
E  General Shoppers         40 customers   2–4 orders each    mixed, no special pattern

Total                      200 customers  ~750 orders
"""

import sys
import os
import json
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import func
from sqlmodel import Session, select, delete
from db import create_db_and_tables, engine
from models.customer import Customer
from models.order import Order
from models.segment import Segment
from models.campaign import Campaign
from models.message import Message

# ── Determinism ──────────────────────────────────────────────────────────────
random.seed(42)

# ── Time anchors ─────────────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def rand_dt(start_days_ago: int, end_days_ago: int) -> datetime:
    """Return a random datetime between two day-offsets from now."""
    lo = min(start_days_ago, end_days_ago)
    hi = max(start_days_ago, end_days_ago)
    delta = random.randint(lo, hi)
    jitter_hours = random.randint(0, 23)
    jitter_mins = random.randint(0, 59)
    return NOW - timedelta(days=delta, hours=jitter_hours, minutes=jitter_mins)


# ── Brand data ────────────────────────────────────────────────────────────────

PRODUCT_CATEGORIES = ["moisturiser", "serum", "spf", "cleanser", "toner"]

# INR price bands per category — reflect real D2C skincare pricing
PRICE_RANGES: dict[str, tuple[int, int]] = {
    "serum":       (799,  3499),
    "moisturiser": (499,  1999),
    "spf":         (399,  1199),
    "cleanser":    (299,   799),
    "toner":       (399,   999),
}

# Metro-heavy city distribution matching Indian skincare D2C buyer patterns
CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune",
    "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Surat",
    "Kochi", "Chandigarh", "Lucknow", "Nagpur", "Indore",
]
CITY_WEIGHTS = [18, 15, 14, 10, 9, 8, 6, 4, 4, 3, 3, 2, 2, 1, 1]

GENDERS = ["female", "female", "female", "male", "male", "other"]
# Skincare D2C skews female ~50%, male ~33%, other ~17%

FIRST_NAMES_F = [
    "Priya", "Ananya", "Meera", "Kavya", "Sneha", "Divya", "Pooja",
    "Riya", "Nisha", "Simran", "Aisha", "Shreya", "Aarti", "Neha",
    "Tanya", "Swati", "Pallavi", "Ankita", "Vidya", "Ritika",
    "Sanya", "Jhanvi", "Manya", "Kriti", "Ishita", "Tanvi", "Aditi",
    "Radhika", "Shweta", "Nidhi",
]
FIRST_NAMES_M = [
    "Arjun", "Rahul", "Amit", "Rohit", "Vikram", "Suresh", "Aditya",
    "Karan", "Nikhil", "Rajesh", "Sanjay", "Deepak", "Manish", "Vivek",
    "Harsh", "Akash", "Ravi", "Piyush", "Gaurav", "Kartik",
    "Sidharth", "Varun", "Pranav", "Yash", "Dhruv",
]
FIRST_NAMES_O = [
    "Avni", "Arin", "Ayan", "Rehan", "Sasha", "Zara", "Noor",
]

LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Verma", "Gupta", "Kumar", "Joshi",
    "Mehta", "Desai", "Nair", "Reddy", "Iyer", "Kapoor", "Bhat",
    "Rao", "Malhotra", "Agarwal", "Shah", "Pandey", "Mishra",
    "Pillai", "Menon", "Trivedi", "Saxena", "Choudhary",
]

EMAIL_DOMAINS = ["gmail.com", "yahoo.in", "hotmail.com", "outlook.com"]

# ── Helpers ───────────────────────────────────────────────────────────────────

_email_counter: dict[str, int] = {}


def gen_email(first: str, last: str) -> str:
    """Generate a unique email for this name combination."""
    key = f"{first.lower()}.{last.lower()}"
    _email_counter[key] = _email_counter.get(key, 0) + 1
    suffix = "" if _email_counter[key] == 1 else str(_email_counter[key])
    domain = random.choice(EMAIL_DOMAINS)
    return f"{key}{suffix}@{domain}"


def gen_phone() -> str:
    """Indian 10-digit mobile number (starts with 6–9)."""
    return str(random.choice([6, 7, 8, 9])) + "".join(
        str(random.randint(0, 9)) for _ in range(9)
    )


def gen_amount(category: str) -> float:
    lo, hi = PRICE_RANGES[category]
    # Round to nearest 49 or 99 to mimic D2C pricing psychology
    raw = random.randint(lo, hi)
    base = (raw // 100) * 100
    return float(random.choice([base + 49, base + 99, base + 149, base + 199]))


def gen_order_status() -> str:
    return random.choices(
        ["completed", "returned", "cancelled"],
        weights=[80, 10, 10],
    )[0]


def pick_first_name(gender: str) -> str:
    if gender == "female":
        return random.choice(FIRST_NAMES_F)
    if gender == "male":
        return random.choice(FIRST_NAMES_M)
    return random.choice(FIRST_NAMES_O)


def build_customer(
    gender: str,
    city: str,
    joined_days_ago_range: tuple[int, int],
    tags: list[str],
) -> Customer:
    first = pick_first_name(gender)
    last = random.choice(LAST_NAMES)
    return Customer(
        name=f"{first} {last}",
        email=gen_email(first, last),
        phone=gen_phone(),
        city=city,
        gender=gender,
        created_at=rand_dt(*joined_days_ago_range),
        tags=json.dumps(tags),
    )


def build_orders_for_customer(
    customer_id: str,
    n_orders: int,
    date_range: tuple[int, int],
    category_weights: dict[str, int] | None = None,
) -> list[Order]:
    """
    Build `n_orders` Order objects for a customer.
    category_weights: optional dict mapping category → relative weight.
    """
    categories = PRODUCT_CATEGORIES
    weights = (
        [category_weights.get(c, 1) for c in categories]
        if category_weights
        else None
    )
    orders = []
    for _ in range(n_orders):
        category = random.choices(categories, weights=weights)[0]
        orders.append(
            Order(
                customer_id=customer_id,
                amount=gen_amount(category),
                product_category=category,
                status=gen_order_status(),
                created_at=rand_dt(*date_range),
            )
        )
    return orders


def attach_aggregates(customer: Customer, orders: list[Order]) -> Customer:
    """Update cached aggregate fields on a customer from its order list."""
    if not orders:
        return customer
    customer.total_orders = len(orders)
    customer.total_spend = round(sum(o.amount for o in orders), 2)
    customer.last_order_date = max(o.created_at for o in orders)
    return customer


# ── Cohort generators ─────────────────────────────────────────────────────────

def cohort_loyal() -> tuple[list[Customer], list[Order]]:
    """
    Cohort A — Loyal Repeat Buyers (40 customers)
    High order count, recent activity, broad category mix.
    """
    customers, all_orders = [], []
    for _ in range(40):
        gender = random.choice(GENDERS)
        city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
        c = build_customer(
            gender=gender,
            city=city,
            joined_days_ago_range=(365, 1080),
            tags=["loyal"],
        )
        n = random.randint(5, 10)
        orders = build_orders_for_customer(
            customer_id=c.id,
            n_orders=n,
            date_range=(1, 30),  # most recent order within last month
        )
        # Scatter older orders too so history looks realistic
        if n > 3:
            old_orders = build_orders_for_customer(
                customer_id=c.id,
                n_orders=random.randint(2, 4),
                date_range=(31, 365),
            )
            orders = old_orders + orders

        c = attach_aggregates(c, orders)
        customers.append(c)
        all_orders.extend(orders)
    return customers, all_orders


def cohort_lapsed() -> tuple[list[Customer], list[Order]]:
    """
    Cohort B — Lapsed High-Value Customers (50 customers)
    Were active and spent well; last order was 3–12 months ago.
    Skews toward serum and moisturiser (higher-value purchases).
    """
    customers, all_orders = [], []
    for _ in range(50):
        gender = random.choice(GENDERS)
        city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
        c = build_customer(
            gender=gender,
            city=city,
            joined_days_ago_range=(365, 900),
            tags=["lapsed", "high-value"],
        )
        orders = build_orders_for_customer(
            customer_id=c.id,
            n_orders=random.randint(3, 6),
            date_range=(91, 365),
            category_weights={"serum": 5, "moisturiser": 4, "spf": 2, "cleanser": 1, "toner": 1},
        )
        c = attach_aggregates(c, orders)
        customers.append(c)
        all_orders.extend(orders)
    return customers, all_orders


def cohort_new() -> tuple[list[Customer], list[Order]]:
    """
    Cohort C — Recent First-Timers (40 customers)
    Just joined; 1–2 orders, all within the last 30 days.
    Skews toward entry-level products (cleanser, toner, spf).
    """
    customers, all_orders = [], []
    for _ in range(40):
        gender = random.choice(GENDERS)
        city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
        c = build_customer(
            gender=gender,
            city=city,
            joined_days_ago_range=(1, 60),
            tags=["new"],
        )
        orders = build_orders_for_customer(
            customer_id=c.id,
            n_orders=random.randint(1, 2),
            date_range=(1, 30),
            category_weights={"cleanser": 4, "toner": 4, "spf": 3, "moisturiser": 2, "serum": 1},
        )
        c = attach_aggregates(c, orders)
        customers.append(c)
        all_orders.extend(orders)
    return customers, all_orders


def cohort_serum_fans() -> tuple[list[Customer], list[Order]]:
    """
    Cohort D — Serum Enthusiasts (30 customers)
    At least 70 % of orders are serum; moderate recency.
    Useful for product-category campaigns.
    """
    customers, all_orders = [], []
    for _ in range(30):
        gender = random.choice(GENDERS)
        city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
        c = build_customer(
            gender=gender,
            city=city,
            joined_days_ago_range=(90, 720),
            tags=["serum-fan"],
        )
        orders = build_orders_for_customer(
            customer_id=c.id,
            n_orders=random.randint(3, 6),
            date_range=(7, 180),
            category_weights={"serum": 10, "moisturiser": 2, "spf": 1, "cleanser": 1, "toner": 1},
        )
        c = attach_aggregates(c, orders)
        customers.append(c)
        all_orders.extend(orders)
    return customers, all_orders


def cohort_general() -> tuple[list[Customer], list[Order]]:
    """
    Cohort E — General Shoppers (40 customers)
    Mixed behaviour; no special tag. Adds natural noise to the dataset.
    """
    customers, all_orders = [], []
    for _ in range(40):
        gender = random.choice(GENDERS)
        city = random.choices(CITIES, weights=CITY_WEIGHTS)[0]
        c = build_customer(
            gender=gender,
            city=city,
            joined_days_ago_range=(30, 730),
            tags=[],
        )
        orders = build_orders_for_customer(
            customer_id=c.id,
            n_orders=random.randint(2, 4),
            date_range=(1, 400),
        )
        c = attach_aggregates(c, orders)
        customers.append(c)
        all_orders.extend(orders)
    return customers, all_orders


# ── Segment builders ──────────────────────────────────────────────────────────

def compute_count(session: Session, conditions: list[dict], match_mode: str) -> int:
    """
    Compute the customer count for a set of Customer-table-only filter conditions.
    Uses Python-side evaluation after loading all customers to avoid building
    dynamic SQLAlchemy queries before the segment_service is implemented.

    Only handles the operators used by the 5 seed segments below.
    """
    customers = session.exec(select(Customer)).all()
    results = []
    for c in customers:
        tests = []
        for cond in conditions:
            field = cond["field"]
            op = cond["operator"]
            val = cond["value"]
            attr = getattr(c, field, None)

            if op == "greater_than":
                tests.append(attr is not None and attr > val)
            elif op == "greater_than_or_equal":
                tests.append(attr is not None and attr >= val)
            elif op == "less_than":
                tests.append(attr is not None and attr < val)
            elif op == "less_than_or_equal":
                tests.append(attr is not None and attr <= val)
            elif op == "equals":
                tests.append(str(attr) == str(val))
            elif op == "more_than_days_ago":
                tests.append(
                    attr is not None and attr < NOW - timedelta(days=val)
                )
            elif op == "less_than_days_ago":
                tests.append(
                    attr is not None and attr >= NOW - timedelta(days=val)
                )
            else:
                tests.append(False)

        if match_mode == "ALL":
            results.append(all(tests))
        else:
            results.append(any(tests))

    return sum(results)


def build_segments(session: Session) -> list[Segment]:
    """
    Five pre-built demo segments that map directly onto the seeded cohorts
    and showcase the full range of supported filter operators.
    """
    defs = [
        {
            "name": "Loyal Repeat Buyers",
            "description": "Customers with 5 or more completed orders — core brand loyalists.",
            "match_mode": "ALL",
            "filters": [
                {"field": "total_orders", "operator": "greater_than_or_equal", "value": 5},
            ],
            "ai_reasoning": (
                "Customers who have ordered 5 or more times are proven brand loyalists. "
                "They respond well to early access and loyalty reward campaigns."
            ),
        },
        {
            "name": "Lapsed High-Value",
            "description": "High-spending customers who haven't ordered in over 90 days.",
            "match_mode": "ALL",
            "filters": [
                {"field": "last_order_date", "operator": "more_than_days_ago", "value": 90},
                {"field": "total_spend", "operator": "greater_than", "value": 3000},
            ],
            "ai_reasoning": (
                "These customers have demonstrated high willingness to spend but have gone quiet. "
                "A win-back campaign with a personalised offer has strong ROI potential."
            ),
        },
        {
            "name": "Recent First-Timers",
            "description": "New customers who made their first purchase in the last 30 days.",
            "match_mode": "ALL",
            "filters": [
                {"field": "last_order_date", "operator": "less_than_days_ago", "value": 30},
                {"field": "total_orders", "operator": "less_than_or_equal", "value": 2},
            ],
            "ai_reasoning": (
                "The first 30 days after acquisition are critical for retention. "
                "An education-first campaign that explains the product range builds "
                "long-term loyalty before competitors can re-target them."
            ),
        },
        {
            "name": "High Spenders",
            "description": "Customers whose total lifetime spend exceeds ₹5,000.",
            "match_mode": "ALL",
            "filters": [
                {"field": "total_spend", "operator": "greater_than", "value": 5000},
            ],
            "ai_reasoning": (
                "Top-spenders drive disproportionate revenue. They are the right audience "
                "for new premium launches, exclusive bundles, and VIP community invites."
            ),
        },
        {
            "name": "Mumbai Shoppers",
            "description": "All customers based in Mumbai.",
            "match_mode": "ALL",
            "filters": [
                {"field": "city", "operator": "equals", "value": "Mumbai"},
            ],
            "ai_reasoning": (
                "Mumbai has the highest customer density. A city-specific campaign can "
                "reference local events or humidity-related skin concerns to drive relevance."
            ),
        },
    ]

    segments = []
    for d in defs:
        count = compute_count(session, d["filters"], d["match_mode"])
        seg = Segment(
            name=d["name"],
            description=d["description"],
            match_mode=d["match_mode"],
            filters=json.dumps(d["filters"]),
            customer_count=count,
            ai_reasoning=d["ai_reasoning"],
        )
        segments.append(seg)
    return segments


# ── Clear helpers ─────────────────────────────────────────────────────────────

def clear_all(session: Session) -> None:
    """
    Delete all seeded data in dependency order so FK constraints are satisfied.
    messages → campaigns → orders → customers → segments
    """
    session.exec(delete(Message))
    session.exec(delete(Campaign))
    session.exec(delete(Order))
    session.exec(delete(Customer))
    session.exec(delete(Segment))
    session.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

def seed_if_empty() -> None:
    """Seed demo data on first boot when the DB has no customers (e.g. Railway deploy)."""
    create_db_and_tables()
    with Session(engine) as session:
        if session.exec(select(func.count(Customer.id))).one() > 0:
            return
    seed()


def seed() -> None:
    create_db_and_tables()

    with Session(engine) as session:
        print("Clearing existing data…")
        clear_all(session)

        print("Generating customers and orders…")
        all_customers: list[Customer] = []
        all_orders: list[Order] = []

        for cohort_fn, label in [
            (cohort_loyal,       "A — Loyal Repeat Buyers"),
            (cohort_lapsed,      "B — Lapsed High-Value"),
            (cohort_new,         "C — Recent First-Timers"),
            (cohort_serum_fans,  "D — Serum Enthusiasts"),
            (cohort_general,     "E — General Shoppers"),
        ]:
            customers, orders = cohort_fn()
            all_customers.extend(customers)
            all_orders.extend(orders)
            print(f"  Cohort {label}: {len(customers)} customers, {len(orders)} orders")

        session.add_all(all_customers)
        session.add_all(all_orders)
        session.commit()

        print(f"\nTotal: {len(all_customers)} customers, {len(all_orders)} orders")

        print("\nGenerating segments…")
        segments = build_segments(session)
        session.add_all(segments)
        session.commit()

        print("Segments created:")
        for seg in segments:
            print(f"  {seg.name!r}: {seg.customer_count} customers")

        print("\nSeed complete.")


if __name__ == "__main__":
    seed()
