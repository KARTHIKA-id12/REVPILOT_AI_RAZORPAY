"""The closed-set schema a real LLM's intent-classification output is
validated against before anything downstream trusts it. This is
deliberately tiny: the model may only ever pick a `intent` name from a
fixed enum, plus at most one bounded numeric field (`discount_percent`,
clamped to 0-100 by the field constraint itself, so an out-of-range or
non-numeric value fails validation and the caller falls back to the
keyword router rather than accepting it).

No product IDs, customer IDs, opportunity IDs, or currency amounts are
ever accepted here -- those always come from a real database lookup in
app/agents/service.py, never from model output. This is what makes the
provider swap (mock keyword router <-> free open-model LLM) safe: the
blast radius of a bad or adversarial model response is capped at "pick
the wrong intent name" or "clamp to 0-100%", not "invent a price."
"""
from typing import Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "CREATE_CAMPAIGN_DRAFT",
    "VIEW_OPPORTUNITIES",
    "VIEW_REVENUE",
    "VIEW_SEGMENTS",
    "SIMULATE_CAMPAIGN",
    "PRODUCT_LOOKUP",
    "UNKNOWN",
]


class ParsedIntent(BaseModel):
    intent: IntentName
    discount_percent: float | None = Field(default=None, ge=0, le=100)
