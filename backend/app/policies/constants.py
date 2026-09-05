"""Canonical registries. Settings endpoints validate every incoming
action_code / policy code against these — an unrecognized code is
rejected outright, never silently stored. This closes a real loophole:
without this validation, a client could create a permission or policy row
for a made-up code that the Action Pipeline never checks, giving the
merchant false confidence that a control exists when it does nothing.
"""

PERMISSION_ACTION_CODES: dict[str, str] = {
    "VIEW_ANALYTICS": "Read revenue metrics, trends, and reports.",
    "VIEW_CUSTOMERS": "Read customer profiles and segments.",
    "VIEW_PRODUCTS": "Read product catalog and inventory.",
    "CREATE_CAMPAIGN_DRAFT": "Draft a campaign proposal (no financial commitment yet).",
    "SIMULATE_CAMPAIGN": "Run what-if revenue simulations (pure computation, no side effects).",
    "CREATE_DISCOUNT": "Commit a campaign's discount and submit it for execution.",
    "CREATE_PAYMENT_LINK": "Create a real (or demo-mode) payment link.",
    "CREATE_ORDER": "Create an order on the customer's behalf.",
    "EXECUTE_FINANCIAL_ACTION": "Any financial action not covered by a more specific code.",
    "CANCEL_PAYMENT_LINK": "Cancel an existing payment link.",
    "REFUND_PAYMENT": "Refund a completed payment.",
    "MODIFY_PRODUCT_PRICE": "Change a product's listed price.",
}

PERMISSION_MODES = {"ALLOW", "APPROVAL", "DENY"}

# code -> (label, value type, min, max) for UI rendering and validation.
POLICY_DEFINITIONS: dict[str, dict] = {
    "MAX_DISCOUNT_PERCENT": {"label": "Maximum discount percent", "type": "percent", "min": 0, "max": 100},
    "MAX_CAMPAIGN_BUDGET": {"label": "Maximum campaign budget (₹)", "type": "amount", "min": 0, "max": None},
    "MAX_DAILY_CAMPAIGNS": {"label": "Maximum campaigns per day", "type": "count", "min": 0, "max": None},
    "MAX_SINGLE_TRANSACTION": {"label": "Maximum single transaction (₹)", "type": "amount", "min": 0, "max": None},
    "REQUIRE_APPROVAL_FOR_FINANCIAL_ACTIONS": {"label": "Require approval for financial actions", "type": "boolean"},
    "NO_OUT_OF_STOCK_PRODUCTS": {"label": "Block campaigns targeting out-of-stock products", "type": "boolean"},
    "NO_NEGATIVE_MARGIN_ACTIONS": {"label": "Block actions with negative margin", "type": "boolean"},
}
