from app.campaigns.simulation import compare_discount_scenarios, simulate_campaign


def test_simulation_math_matches_spec_formula():
    result = simulate_campaign(
        eligible_customers=100, average_order_value=2000, discount_percent=10, organic_confidence=0.5,
    )
    expected_conversion = min(0.6, 0.5 * 0.6)  # 0.3
    assert result.expected_conversion == expected_conversion
    assert result.expected_orders == 100 * expected_conversion
    assert result.expected_revenue == result.expected_orders * 2000
    assert result.discount_cost == result.expected_revenue * 0.10


def test_zero_campaign_cost_gives_none_roi_not_infinity():
    """A 0% discount campaign has zero cost — ROI must be reported as
    undefined (None), never a fabricated infinite or zero value."""
    result = simulate_campaign(eligible_customers=50, average_order_value=1000, discount_percent=0, organic_confidence=0.4)
    assert result.discount_cost == 0
    assert result.roi is None


def test_higher_discount_increases_cost_and_can_reduce_roi():
    low = simulate_campaign(eligible_customers=100, average_order_value=2000, discount_percent=10, organic_confidence=0.5)
    high = simulate_campaign(eligible_customers=100, average_order_value=2000, discount_percent=20, organic_confidence=0.5)
    assert high.discount_cost > low.discount_cost
    # revenue and conversion identical (discount doesn't change conversion in this model),
    # so a bigger discount cost against the same revenue means lower ROI
    assert high.roi < low.roi


def test_conversion_is_capped_even_with_very_high_organic_confidence():
    result = simulate_campaign(eligible_customers=10, average_order_value=500, discount_percent=10, organic_confidence=5.0)
    assert result.expected_conversion == 0.6  # capped, never "3.0" (300% conversion)


def test_deterministic_same_inputs_same_output():
    a = simulate_campaign(eligible_customers=77, average_order_value=1234.56, discount_percent=12, organic_confidence=0.42)
    b = simulate_campaign(eligible_customers=77, average_order_value=1234.56, discount_percent=12, organic_confidence=0.42)
    assert a.as_dict() == b.as_dict()


def test_what_if_comparison_across_discounts():
    scenarios = compare_discount_scenarios(
        eligible_customers=100, average_order_value=2000, organic_confidence=0.5, discount_percents=[10, 12, 15],
    )
    assert len(scenarios) == 3
    assert [s["discount_percent"] for s in scenarios] == [10, 12, 15]
    # cost should increase monotonically with discount at fixed revenue
    costs = [s["discount_cost"] for s in scenarios]
    assert costs == sorted(costs)


def test_every_result_labeled_estimated_not_presented_as_fact():
    result = simulate_campaign(eligible_customers=10, average_order_value=500, discount_percent=10, organic_confidence=0.3)
    assert result.as_dict()["label"] == "ESTIMATED"
