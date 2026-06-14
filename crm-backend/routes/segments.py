import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from db import get_session
from models.customer import Customer
from models.segment import Segment
from schemas import (
    FilterCondition,
    SegmentCreate,
    SegmentInterpretRequest,
    SegmentInterpretResponse,
    SegmentOut,
    SegmentPreviewRequest,
    SegmentPreviewResponse,
    SegmentPreviewCustomer,
)
from services import ai_service, segment_service

router = APIRouter(tags=["segments"])


# ── GET /api/segments ─────────────────────────────────────────────────────────

@router.get("/segments", response_model=list[SegmentOut])
def list_segments(session: Session = Depends(get_session)) -> list[SegmentOut]:
    segments = session.exec(select(Segment).order_by(Segment.created_at.desc())).all()
    return [SegmentOut.model_validate(s) for s in segments]


# ── POST /api/segments/interpret ─────────────────────────────────────────────
# Registered before /{segment_id} (same router, different method — no conflict,
# but literal paths before parameterised ones is a good habit).

@router.post("/segments/interpret", response_model=SegmentInterpretResponse)
async def interpret_segment(
    body: SegmentInterpretRequest,
    session: Session = Depends(get_session),
) -> SegmentInterpretResponse:
    # Build lightweight context: total customer count for prompt grounding
    context = body.context or {}
    if "total_customers" not in context:
        context["total_customers"] = session.exec(
            select(func.count(Customer.id))
        ).one()

    result = await ai_service.interpret_segment(body.intent_text, context)

    return SegmentInterpretResponse(
        name=result["name"],
        filters=[FilterCondition(**f) for f in result["filters"]],
        match_mode=result.get("match_mode", "ALL"),
        explanation=result["explanation"],
    )


# ── POST /api/segments/preview ───────────────────────────────────────────────
# Registered before /{segment_id} so the literal path wins over the param.

@router.post("/segments/preview", response_model=SegmentPreviewResponse)
def preview_segment(
    body: SegmentPreviewRequest,
    session: Session = Depends(get_session),
) -> SegmentPreviewResponse:
    """
    Evaluate filters without persisting anything.
    Returns the total matching count and up to 5 customer names for live preview.
    """
    filters_json = json.dumps([f.model_dump() for f in body.filters])
    try:
        customers = segment_service.evaluate_filters(
            session, filters_json, body.match_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return SegmentPreviewResponse(
        count=len(customers),
        customers=[SegmentPreviewCustomer.model_validate(c) for c in customers[:5]],
    )


# ── GET /api/segments/{id} ────────────────────────────────────────────────────

@router.get("/segments/{segment_id}", response_model=SegmentOut)
def get_segment(
    segment_id: str,
    session: Session = Depends(get_session),
) -> SegmentOut:
    seg = session.get(Segment, segment_id)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Recompute and refresh the cached count on every detail fetch
    fresh_count = segment_service.compute_customer_count(
        session, seg.filters, seg.match_mode
    )
    if fresh_count != seg.customer_count:
        seg.customer_count = fresh_count
        session.add(seg)
        session.commit()
        session.refresh(seg)

    return SegmentOut.model_validate(seg)


# ── POST /api/segments ────────────────────────────────────────────────────────

@router.post("/segments", status_code=201, response_model=SegmentOut)
def create_segment(
    body: SegmentCreate,
    session: Session = Depends(get_session),
) -> SegmentOut:
    filters_json = json.dumps([f.model_dump() for f in body.filters])

    # Validate filters and compute count before persisting
    try:
        count = segment_service.compute_customer_count(
            session, filters_json, body.match_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    seg = Segment(
        name=body.name,
        description=body.description,
        filters=filters_json,
        match_mode=body.match_mode,
        customer_count=count,
        ai_reasoning=body.ai_reasoning,
    )
    session.add(seg)
    session.commit()
    session.refresh(seg)

    return SegmentOut.model_validate(seg)
