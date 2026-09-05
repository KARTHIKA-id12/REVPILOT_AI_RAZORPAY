"""Closed schema for LLM-extracted AI Buyer intent. The model may only
ever propose a bounded budget number and a short list of search
keywords -- it never sees or invents a product ID, a price, or stock
status. Ranking, pricing, and availability always come from
app.buyer.service._rank_products() against the real catalog; this schema
only widens *which terms* are matched against that real data.
"""
from pydantic import BaseModel, Field


class BuyerIntent(BaseModel):
    max_budget: float | None = Field(default=None, ge=0)
    search_terms: list[str] = Field(default_factory=list, max_length=8)
