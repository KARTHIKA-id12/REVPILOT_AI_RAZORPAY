"""Deterministic campaign simulation. Implements the spec's formula
exactly:

    Expected Orders = Eligible Customers x Expected Conversion
    Expected Revenue = Expected Orders x Average Order Value
    Discount Cost = Expected Revenue x Discount Rate
    Expected Incremental Revenue = Expected Revenue - Baseline Revenue
    ROI = Expected Incremental Revenue / Campaign Cost

No LLM involvement, no randomness — same inputs always produce the same
output, which is what lets what-if comparisons ("10% vs 12%") be trusted.

Loophole deliberately closed: this function takes primitive numbers
(reach, AOV, conversion) that the CALLER must have sourced from real DB
queries — it does not accept a free-form "estimated_revenue" from the
agent and pass it through. app/agents/pipeline.py always calls this with
freshly recomputed inputs, never with a number the agent supplied.
"""

from dataclasses import dataclass


@dataclass
class SimulationResult:
    eligible_customers: int
    expected_conversion: float
    expected_orders: float
    average_order_value: float
    expected_revenue: float
    discount_percent: float
    discount_cost: float
    baseline_revenue: float
    expected_incremental_revenue: float
    campaign_cost: float
    roi: float | None  # None when campaign_cost is 0 (division undefined, not "infinite ROI")
    assumptions: dict

    def as_dict(self) -> dict:
        return {
            "eligible_customers": self.eligible_customers,
            "expected_conversion": round(self.expected_conversion, 4),
            "expected_orders": round(self.expected_orders, 2),
            "average_order_value": round(self.average_order_value, 2),
            "expected_revenue": round(self.expected_revenue, 2),
            "discount_percent": self.discount_percent,
            "discount_cost": round(self.discount_cost, 2),
            "baseline_revenue": round(self.baseline_revenue, 2),
            "expected_incremental_revenue": round(self.expected_incremental_revenue, 2),
            "campaign_cost": round(self.campaign_cost, 2),
            "roi": round(self.roi, 2) if self.roi is not None else None,
            "assumptions": self.assumptions,
            "label": "ESTIMATED",
        }


def simulate_campaign(
    *,
    eligible_customers: int,
    average_order_value: float,
    discount_percent: float,
    organic_confidence: float,
    baseline_conversion_rate: float = 0.0,
    campaign_response_dampener: float = 0.6,
) -> SimulationResult:
    """
    eligible_customers: real reach count from the DB (e.g. opportunity.reach_count).
    average_order_value: real historical AOV for the relevant segment/product.
    organic_confidence: real affinity confidence observed in transactions (0-1).
    baseline_conversion_rate: what would have converted anyway with no campaign
        (0 if there's no defensible baseline — see docs/ai-decisions.md
        ESTIMATED vs ATTRIBUTED distinction; we do not invent a baseline).
    campaign_response_dampener: a targeted campaign is conservatively assumed
        to convert at a discount to naturally observed co-purchase behavior.
    """
    discount_rate = discount_percent / 100
    effective_dampener = campaign_response_dampener + (discount_rate * 2.0)
    expected_conversion = min(0.8, organic_confidence * effective_dampener)
    expected_orders = eligible_customers * expected_conversion
    expected_revenue = expected_orders * average_order_value
    discount_cost = expected_revenue * discount_rate

    baseline_orders = eligible_customers * baseline_conversion_rate
    baseline_revenue = baseline_orders * average_order_value
    expected_incremental_revenue = expected_revenue - baseline_revenue

    campaign_cost = discount_cost
    roi = (expected_incremental_revenue / campaign_cost) if campaign_cost > 0 else None

    return SimulationResult(
        eligible_customers=eligible_customers,
        expected_conversion=expected_conversion,
        expected_orders=expected_orders,
        average_order_value=average_order_value,
        expected_revenue=expected_revenue,
        discount_percent=discount_percent,
        discount_cost=discount_cost,
        baseline_revenue=baseline_revenue,
        expected_incremental_revenue=expected_incremental_revenue,
        campaign_cost=campaign_cost,
        roi=roi,
        assumptions={
            "expected_conversion_formula": f"min(0.6, organic_confidence[{organic_confidence}] x dampener[{campaign_response_dampener}])",
            "baseline_conversion_rate": baseline_conversion_rate,
            "note": "expected_incremental_revenue is a projection, not a measured fact — "
            "see docs/ai-decisions.md for the ESTIMATED vs ATTRIBUTED distinction.",
        },
    )


def compare_discount_scenarios(
    *, eligible_customers: int, average_order_value: float, organic_confidence: float, discount_percents: list[float],
) -> list[dict]:
    """What-if comparison across multiple discount levels — same
    deterministic function, just called repeatedly. This is what powers
    "what happens if I offer 12% instead of 10%?"."""
    results = []
    for pct in discount_percents:
        sim = simulate_campaign(
            eligible_customers=eligible_customers, average_order_value=average_order_value,
            discount_percent=pct, organic_confidence=organic_confidence,
        )
        results.append(sim.as_dict())
    return results
