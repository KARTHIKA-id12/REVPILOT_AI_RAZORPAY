"""Risk classification. This labels actions for audit/UI purposes and
feeds the Emergency Stop's financial-action set — it does NOT independently
gate execution. The permission engine (app/policies/permissions.py) is the
single source of truth for whether approval is required; risk_level here
exists so the merchant can see *why* something feels risky in the UI and
so audit logs carry a consistent severity signal."""

READ_ACTION_CODES = {
    "VIEW_ANALYTICS", "VIEW_CUSTOMERS", "VIEW_PRODUCTS", "SIMULATE_CAMPAIGN",
}
MEDIUM_ACTION_CODES = {"CREATE_CAMPAIGN_DRAFT", "CREATE_DISCOUNT"}
HIGH_ACTION_CODES = {"CREATE_PAYMENT_LINK", "CREATE_ORDER", "CANCEL_PAYMENT_LINK"}
CRITICAL_ACTION_CODES = {"REFUND_PAYMENT", "MODIFY_PRODUCT_PRICE", "EXECUTE_FINANCIAL_ACTION"}


def classify_risk(action_code: str, amount: float | None = None, single_txn_cap: float = 10000) -> str:
    if action_code in CRITICAL_ACTION_CODES:
        return "critical"
    if amount is not None and amount > single_txn_cap:
        return "critical"
    if action_code in HIGH_ACTION_CODES:
        return "high"
    if action_code in MEDIUM_ACTION_CODES:
        return "medium"
    return "low"
