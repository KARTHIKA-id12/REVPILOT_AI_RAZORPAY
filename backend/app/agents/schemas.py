"""Structured tool I/O schemas. Every action the agent proposes MUST
validate against one of these models. If the model's JSON output doesn't
parse and validate cleanly, the tool call is rejected before it reaches
any service — the agent gets a validation error back and must retry, it
is never silently coerced or "interpreted charitably".

Note what is deliberately NOT accepted from the agent on any action model:
there is no `estimated_revenue`, `final_amount`, or similar financial
output field here. The agent may reference numbers in its reasoning text,
but the pipeline never reads a financial figure out of the agent's
payload — every amount is recomputed server-side from `product_ids` /
`discount_percent` / `opportunity_id` against current DB state.
"""

import uuid

from pydantic import BaseModel, Field, field_validator


class CreateCampaignDraftInput(BaseModel):
    opportunity_id: uuid.UUID | None = None
    name: str = Field(min_length=3, max_length=255)
    objective: str = Field(min_length=3, max_length=100)
    segment_code: str | None = None
    product_ids: list[uuid.UUID] = Field(min_length=1)
    discount_percent: float = Field(ge=0, le=100)
    budget_amount: float = Field(ge=0)


class SimulateCampaignInput(BaseModel):
    opportunity_id: uuid.UUID | None = None
    product_ids: list[uuid.UUID] = Field(min_length=1)
    discount_percent: float = Field(ge=0, le=100)
    segment_code: str | None = None

    @field_validator("discount_percent")
    @classmethod
    def sane_discount(cls, v: float) -> float:
        # Sanity bound independent of merchant policy — a request for a
        # 500% discount is a malformed request, not a policy question.
        if v > 100:
            raise ValueError("discount_percent cannot exceed 100")
        return v


class RequestCampaignApprovalInput(BaseModel):
    campaign_id: uuid.UUID


class ApproveOrRejectInput(BaseModel):
    approval_id: uuid.UUID
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = None


class PauseCampaignInput(BaseModel):
    campaign_id: uuid.UUID


class CancelCampaignInput(BaseModel):
    campaign_id: uuid.UUID


class GetProductDetailsInput(BaseModel):
    product_id: uuid.UUID | None = None
    product_name_query: str | None = None


class GetCustomerProfileInput(BaseModel):
    customer_id: uuid.UUID


# Read-tool inputs that take no parameters still get an (empty) schema so
# every tool call — read or action — goes through the same validation gate.
class NoInput(BaseModel):
    pass
