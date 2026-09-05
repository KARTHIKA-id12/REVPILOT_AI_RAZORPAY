"""Deterministic policy engine. Every check here is a pure function over
plain data — no LLM call, no ambiguity, no way for a persuasive prompt to
change the outcome. The Action Pipeline (app/agents/pipeline.py) treats a
failed PolicyResult as absolute: execution stops, full stop, regardless of
what the agent's stated reasoning was.

Loophole checklist deliberately closed here:
- Policy values are read from the DB per-merchant, never from the agent's
  request payload (an agent claiming "policy allows 20%" cannot make it so).
- Every numeric check compares against the CURRENT stored policy row, not
  a cached/prior value — re-read on every call.
- Stock and margin checks look at CURRENT product state, not a snapshot
  the agent might have seen several turns ago.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.campaigns import PolicyRule
from app.models.catalog import Product


@dataclass
class PolicyResult:
    passed: bool
    violations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "violations": self.violations}


def _get_policy_value(db: Session, merchant_id: uuid.UUID, code: str, default):
    rule = db.query(PolicyRule).filter(PolicyRule.merchant_id == merchant_id, PolicyRule.code == code).one_or_none()
    if rule is None:
        return default
    return rule.value_json.get("value", default)


def check_discount_percent(db: Session, merchant_id: uuid.UUID, discount_percent: float) -> PolicyResult:
    max_discount = _get_policy_value(db, merchant_id, "MAX_DISCOUNT_PERCENT", 15)
    if discount_percent > max_discount:
        return PolicyResult(False, [f"Discount {discount_percent}% exceeds MAX_DISCOUNT_PERCENT ({max_discount}%)."])
    if discount_percent < 0:
        return PolicyResult(False, ["Discount cannot be negative."])
    return PolicyResult(True)


def check_campaign_budget(db: Session, merchant_id: uuid.UUID, budget_amount: float) -> PolicyResult:
    max_budget = _get_policy_value(db, merchant_id, "MAX_CAMPAIGN_BUDGET", 5000)
    if budget_amount > max_budget:
        return PolicyResult(False, [f"Budget ₹{budget_amount:,.2f} exceeds MAX_CAMPAIGN_BUDGET (₹{max_budget:,.2f})."])
    return PolicyResult(True)


def check_daily_campaign_count(db: Session, merchant_id: uuid.UUID, campaigns_created_today: int) -> PolicyResult:
    max_daily = _get_policy_value(db, merchant_id, "MAX_DAILY_CAMPAIGNS", 50)
    if campaigns_created_today >= max_daily:
        return PolicyResult(False, [f"Daily campaign limit reached ({campaigns_created_today}/{max_daily})."])
    return PolicyResult(True)


def check_single_transaction(db: Session, merchant_id: uuid.UUID, amount: float) -> PolicyResult:
    max_txn = _get_policy_value(db, merchant_id, "MAX_SINGLE_TRANSACTION", 10000)
    if amount > max_txn:
        return PolicyResult(False, [f"Transaction amount ₹{amount:,.2f} exceeds MAX_SINGLE_TRANSACTION (₹{max_txn:,.2f})."])
    return PolicyResult(True)


def check_stock_availability(db: Session, merchant_id: uuid.UUID, product_ids: list[uuid.UUID]) -> PolicyResult:
    no_oos_policy = _get_policy_value(db, merchant_id, "NO_OUT_OF_STOCK_PRODUCTS", True)
    if not no_oos_policy or not product_ids:
        return PolicyResult(True)
    out_of_stock = (
        db.query(Product.name)
        .filter(Product.merchant_id == merchant_id, Product.id.in_(product_ids), Product.stock_status == "out_of_stock")
        .all()
    )
    if out_of_stock:
        names = ", ".join(p.name for p in out_of_stock)
        return PolicyResult(False, [f"Out-of-stock product(s) in target set: {names}."])
    return PolicyResult(True)


def run_draft_policy_checks(
    db: Session, merchant_id: uuid.UUID, *, budget_amount: float, product_ids: list[uuid.UUID], campaigns_created_today: int,
) -> PolicyResult:
    """Checks applied at DRAFT time only: budget ceiling, stock
    availability, and daily campaign volume. Deliberately excludes the
    discount cap — CREATE_CAMPAIGN_DRAFT is ALLOW by default (drafting a
    proposal isn't a financial commitment), so a merchant/agent can still
    draft and review a campaign at an out-of-policy discount before the
    real gate (CREATE_DISCOUNT, checked in run_campaign_policy_checks)
    catches it at submission time. Splitting these two checks is what
    keeps the staged safety story intact: BLOCKED only happens at the
    point real financial commitment is being requested, not before."""
    checks = [
        check_campaign_budget(db, merchant_id, budget_amount),
        check_daily_campaign_count(db, merchant_id, campaigns_created_today),
        check_stock_availability(db, merchant_id, product_ids),
    ]
    violations = [v for c in checks for v in c.violations]
    return PolicyResult(passed=len(violations) == 0, violations=violations)


def run_campaign_policy_checks(
    db: Session, merchant_id: uuid.UUID, *, discount_percent: float, budget_amount: float,
    product_ids: list[uuid.UUID], campaigns_created_today: int,
) -> PolicyResult:
    """Full check used when a discount is actually being committed
    (submitting for approval, and again at execution time). All
    violations are collected (not just the first) so the merchant/agent
    sees the complete picture in one pass."""
    checks = [
        check_discount_percent(db, merchant_id, discount_percent),
        check_campaign_budget(db, merchant_id, budget_amount),
        check_daily_campaign_count(db, merchant_id, campaigns_created_today),
        check_stock_availability(db, merchant_id, product_ids),
    ]
    violations = [v for c in checks for v in c.violations]
    return PolicyResult(passed=len(violations) == 0, violations=violations)
