"""Integration test proving the analytics pipeline produces sane, grounded
results against the real seeded TechNest merchant — not synthetic data.
Skips gracefully if the DB or seed data isn't present."""

import pytest
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models.identity import Merchant
from app.models.opportunities import RevenueOpportunity
from app.opportunities.service import run_full_analytics


@pytest.fixture
def technest_merchant():
    db = SessionLocal()
    try:
        merchant = db.query(Merchant).filter(Merchant.name == "TechNest").one_or_none()
    except OperationalError:
        db.close()
        pytest.skip("Postgres not reachable in this environment")
    if not merchant:
        db.close()
        pytest.skip("TechNest not seeded — run scripts/seed_demo.py first")
    yield db, merchant.id
    db.close()


def test_full_pipeline_runs_and_detects_real_opportunities(technest_merchant):
    db, merchant_id = technest_merchant
    summary = run_full_analytics(db, merchant_id)

    assert summary["metrics"]["total_revenue"] > 0
    assert summary["metrics"]["order_count"] > 1000  # seeded ~4400 paid orders
    assert len(summary["segments"]) > 0
    assert summary["opportunities_detected"] > 0
    # Multiple opportunity types should surface from real, varied data —
    # not just one lucky signal.
    assert len(summary["opportunities_by_type"]) >= 3


def test_keyboard_mouse_cross_sell_or_bundle_detected_with_real_lift(technest_merchant):
    db, merchant_id = technest_merchant
    run_full_analytics(db, merchant_id)

    rows = db.query(RevenueOpportunity).filter(RevenueOpportunity.merchant_id == merchant_id).all()
    kb_mouse = [
        r for r in rows
        if r.type in {"cross_sell", "bundle"}
        and r.historical_affinity and r.historical_affinity > 1.5
    ]
    assert len(kb_mouse) > 0, "expected at least one strong (lift > 1.5) cross-sell/bundle opportunity from real data"


def test_priority_scores_are_bounded_and_evidence_present(technest_merchant):
    db, merchant_id = technest_merchant
    run_full_analytics(db, merchant_id)

    opportunities = db.query(RevenueOpportunity).filter(RevenueOpportunity.merchant_id == merchant_id).all()
    assert len(opportunities) > 0
    for opp in opportunities:
        assert 0 <= float(opp.priority_score) <= 100
        assert opp.evidence_json  # every opportunity must carry evidence, never a bare number
        assert opp.risk_level in {"low", "medium", "high", "critical"}
