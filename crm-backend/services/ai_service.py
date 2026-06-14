"""
AI service — OpenAI async wrapper.

Two public entry points
-----------------------
chat()              → AI co-pilot panel: page-aware Q&A and interpretation.
interpret_segment() → NL intent → structured filter JSON + explanation.

Both functions gracefully return a placeholder when OPENAI_API_KEY is not set,
so the rest of the app stays demo-able without a configured key.
"""

import json
import openai

from config import OPENAI_API_KEY, OPENAI_BASE_URL

MODEL = "gpt-4o-mini"

# Lazy client — created once on first call so a missing key does not crash startup.
_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        kwargs: dict = {"api_key": OPENAI_API_KEY}
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL
        _client = openai.AsyncOpenAI(**kwargs)
    return _client


# ── Brand & schema context injected into every prompt ─────────────────────────

_BRAND = """
Bare is an AI-native CRM for a fictional Indian skincare D2C brand.
Products: moisturiser, serum, SPF, cleanser, toner.
Customers are Indian shoppers. Amounts are in INR (₹).
Cities include Mumbai, Delhi, Bangalore, Hyderabad, Pune, Chennai, Kolkata, Jaipur, and others.
""".strip()

_FILTER_SCHEMA = """
Available segment filter fields and operators:

  last_order_date  — more_than_days_ago <int>, less_than_days_ago <int>
  total_spend      — greater_than, greater_than_or_equal, less_than, less_than_or_equal <float>
  total_orders     — greater_than, greater_than_or_equal, less_than, less_than_or_equal, equals <int>
  city             — equals <string>   (e.g. "Mumbai", "Delhi")
  gender           — equals <string>   (male | female | other)
  product_category — equals <string>   (moisturiser | serum | spf | cleanser | toner)

match_mode: "ALL" (every condition must match) or "ANY" (at least one must match)
""".strip()


# ── Co-pilot chat ─────────────────────────────────────────────────────────────

async def chat(
    message: str,
    current_page: str,
    data_context: dict,
    history: list[dict] | None = None,
) -> dict:
    """
    General-purpose AI co-pilot response for the Bare CRM side panel.
    Returns {"assistant_text": str, "suggestions": None}.

    `history` is an ordered list of prior turns: [{"role": "user"|"assistant", "content": str}, ...]
    The backend caps it at 10 entries (5 exchanges) as a safety measure even if the
    frontend sends more.
    """
    if not OPENAI_API_KEY:
        return {
            "assistant_text": (
                "AI co-pilot is not configured. "
                "Add OPENAI_API_KEY to your .env file to enable it."
            ),
            "suggestions": None,
        }

    context_str = json.dumps(data_context, default=str) if data_context else "none"

    system = f"""{_BRAND}

You are the AI co-pilot embedded inside Bare CRM. You help marketers:
- Understand customer cohorts and behaviour patterns
- Suggest and refine audience segments
- Draft personalised campaign copy
- Interpret campaign delivery and engagement performance

Current page the user is viewing: {current_page}
Relevant data the UI is showing: {context_str}

Be concise and specific. Speak like a senior growth advisor, not a generic chatbot.
Lead with the most actionable insight first.
If performance data is present, interpret rates and suggest next actions.
If segment data is present, explain the audience and its campaign potential.
Keep responses under 200 words unless detail is clearly needed.
"""

    # Build the messages list: system + capped history + current user turn.
    _MAX_HISTORY = 10  # last 10 messages = 5 exchange turns
    safe_history: list[dict] = []
    for h in (history or [])[-_MAX_HISTORY:]:
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            safe_history.append({"role": role, "content": content})

    messages_payload = (
        [{"role": "system", "content": system}]
        + safe_history
        + [{"role": "user", "content": message}]
    )

    try:
        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            messages=messages_payload,
        )
        return {
            "assistant_text": response.choices[0].message.content or "",
            "suggestions": None,
        }
    except openai.AuthenticationError:
        return {
            "assistant_text": "OpenAI key is invalid or expired. Check OPENAI_API_KEY in crm-backend/.env.txt.",
            "suggestions": None,
        }
    except openai.RateLimitError:
        return {
            "assistant_text": "OpenAI rate limit or quota reached. Please try again in a moment.",
            "suggestions": None,
        }
    except Exception as exc:
        return {
            "assistant_text": f"AI service error ({type(exc).__name__}). Check the backend logs.",
            "suggestions": None,
        }


# ── Segment interpretation ────────────────────────────────────────────────────

async def interpret_segment(intent_text: str, context: dict) -> dict:
    """
    Convert a natural-language audience description into a structured segment
    filter definition.

    Returns:
      {
        "name": str,
        "filters": [{"field": ..., "operator": ..., "value": ...}, ...],
        "match_mode": "ALL" | "ANY",
        "explanation": str
      }
    """
    if not OPENAI_API_KEY:
        return {
            "name": "New Segment",
            "filters": [],
            "match_mode": "ALL",
            "explanation": (
                "AI service not configured. "
                "Add OPENAI_API_KEY to use natural-language segment building."
            ),
        }

    context_str = json.dumps(context, default=str) if context else "none"

    system = f"""{_BRAND}

{_FILTER_SCHEMA}

You are a CRM segment builder. Convert the marketer's natural-language audience
description into a structured filter definition using ONLY the fields and operators
listed above.

Return ONLY a JSON object — no markdown fences, no prose outside the JSON.
Use this exact structure:

{{
  "name": "short descriptive segment name (3-5 words)",
  "filters": [
    {{"field": "field_name", "operator": "operator_name", "value": <value>}},
    ...
  ],
  "match_mode": "ALL",
  "explanation": "One sentence: who this is and why they matter for a campaign."
}}

Rules:
- Use the minimum number of conditions that precisely define the intent.
- Prefer "ALL" match_mode unless the intent clearly describes an OR relationship.
- For date-based recency ("last ordered 3 months ago"), use more_than_days_ago/less_than_days_ago.
- For spend thresholds, use INR values (e.g. 2000, 5000).

Available context: {context_str}
"""

    try:
        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=512,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": intent_text},
            ],
        )
        raw: str = (response.choices[0].message.content or "").strip()
    except openai.AuthenticationError:
        return {
            "name": "New Segment",
            "filters": [],
            "match_mode": "ALL",
            "explanation": "OpenAI key is invalid or expired. Check OPENAI_API_KEY in crm-backend/.env.txt.",
        }
    except openai.RateLimitError:
        return {
            "name": "New Segment",
            "filters": [],
            "match_mode": "ALL",
            "explanation": "OpenAI rate limit reached. Please try again in a moment.",
        }
    except Exception as exc:
        return {
            "name": "New Segment",
            "filters": [],
            "match_mode": "ALL",
            "explanation": f"AI service error ({type(exc).__name__}). Check the backend logs.",
        }

    # Strip markdown fences if the model wraps the JSON anyway
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

    try:
        parsed = json.loads(raw)
        return {
            "name": parsed.get("name", "New Segment"),
            "filters": parsed.get("filters", []),
            "match_mode": parsed.get("match_mode", "ALL"),
            "explanation": parsed.get("explanation", ""),
        }
    except json.JSONDecodeError:
        # Return partial text as explanation so the UI isn't broken
        return {
            "name": "New Segment",
            "filters": [],
            "match_mode": "ALL",
            "explanation": raw[:400],
        }
