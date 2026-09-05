export interface Merchant {
  id: string;
  name: string;
  category: string;
  description: string | null;
  status: string;
}

export interface DashboardSummary {
  total_revenue: number;
  order_count: number;
  average_order_value: number;
  conversion_rate: number;
  repeat_purchase_rate: number;
  payment_failure_rate: number;
  abandoned_cart_rate: number | null;
  open_opportunities: number;
}

export interface RevenueTrendPoint {
  period: string;
  revenue: number;
}

export interface TopProduct {
  product_id: string;
  name: string;
  sku: string;
  revenue: number;
  units: number;
  orders: number;
}

export interface OpportunityProductRef {
  id: string;
  name: string;
}

export type OpportunityType = "cross_sell" | "bundle" | "abandoned_cart" | "reactivation" | "repeat_purchase";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface Opportunity {
  id: string;
  type: OpportunityType;
  source_product: OpportunityProductRef | null;
  target_product: OpportunityProductRef | null;
  reach_count: number;
  confidence: number;
  historical_affinity: number;
  estimated_conversion: number;
  estimated_revenue_amount: number;
  risk_level: RiskLevel;
  priority_score: number;
  evidence: Record<string, unknown>;
  status: string;
  created_at: string | null;
}

export interface OpportunityListResponse {
  items: Opportunity[];
  page: number;
  page_size: number;
  total: number;
}

export interface SimulationScenario {
  eligible_customers: number;
  expected_conversion: number;
  expected_orders: number;
  average_order_value: number;
  expected_revenue: number;
  discount_percent: number;
  discount_cost: number;
  baseline_revenue: number;
  expected_incremental_revenue: number;
  campaign_cost: number;
  roi: number | null;
  assumptions: Record<string, unknown>;
  label: string;
}

export interface SimulationCompareResponse {
  products: { id: string; name: string }[];
  eligible_customers: number;
  organic_confidence: number;
  scenarios: SimulationScenario[];
  recommended_discount_percent: number | null;
}

export interface CampaignSummary {
  id: string;
  name: string;
  objective: string;
  status: string;
  discount_percent: number;
  budget_amount: number;
  expected_revenue_amount: number;
  actual_revenue_amount: number;
  created_at: string | null;
  starts_at: string | null;
}

export interface CampaignApprovalHistoryEntry {
  id: string;
  status: string;
  risk_level: RiskLevel;
  policy_result: { passed: boolean; violations: string[] };
  created_at: string | null;
  decided_at: string | null;
}

export interface CampaignPaymentEntry {
  id: string;
  provider: string;
  status: string;
  amount: number;
  provider_payment_link_id: string | null;
  created_at: string | null;
}

export interface CampaignAuditEntry {
  action: string;
  tool: string | null;
  reason: string | null;
  result: string;
  error: string | null;
  created_at: string | null;
}

export interface CampaignDetail extends CampaignSummary {
  opportunity_id: string | null;
  products: { id: string; name: string }[];
  approval_history: CampaignApprovalHistoryEntry[];
  payments: CampaignPaymentEntry[];
  audit_trail: CampaignAuditEntry[];
}

export interface PermissionItem {
  action_code: string;
  description: string;
  mode: PermissionMode;
}

export type PermissionMode = "ALLOW" | "APPROVAL" | "DENY";

export interface FailureLabScenario {
  code: string;
  label: string;
  description?: string;
  failure_mode?: string;
  recovery?: string;
}

export interface FailureTraceStep {
  stage: string;
  status: "info" | "ok" | "failure" | "blocked" | "warning";
  detail: string;
}

export interface FailureLabResult {
  trace: FailureTraceStep[];
  scenario?: string;
  label?: string;
  campaign_id?: string;
  final_campaign_status?: string;
}

export type PolicyValueType = "percent" | "amount" | "count" | "boolean";

export interface PolicyItem {
  code: string;
  label: string;
  type: PolicyValueType;
  min: number | null;
  max: number | null;
  value: number | boolean;
}

export interface AgentSessionSummary {
  id: string;
  status: string;
  started_at: string;
}

export interface AgentMessageEntry {
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface AgentMessageResponse {
  reply: string;
  intent: string;
  tool_result?: Record<string, unknown> | null;
  action_id?: string;
  draft_action_id?: string;
  approval_action_id?: string;
  error?: string;
}

export interface BuyerProduct {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  price: { amount: number; currency: string };
  availability: { in_stock: boolean; stock_status: string; quantity: number };
  category: string | null;
  tags: string[];
  use_cases: string[];
  purchase: { available: boolean };
}

export interface BuyerBundle {
  id: string;
  name: string;
  product_ids: string[];
  products: BuyerProduct[];
  total: { amount: number; currency: string };
  reason: string;
}

export interface BuyerQueryResponse {
  query: string;
  intent: { terms: string[]; max_budget: number | null; budget_source: string | null };
  products: BuyerProduct[];
  bundles: BuyerBundle[];
  found: boolean;
  explanation: string;
}

export interface CartItem {
  id: string;
  product_id: string;
  name: string;
  sku: string;
  quantity: number;
  unit_price: { amount: number; currency: string };
  line_total: { amount: number; currency: string };
  availability: { in_stock: boolean; quantity: number; available_for_cart: boolean };
  image_url: string | null;
}

export interface CartState {
  id: string;
  session_ref: string;
  customer_id: string | null;
  status: string;
  items: CartItem[];
  subtotal: { amount: number; currency: string };
  shipping: { amount: number; currency: string };
  total: { amount: number; currency: string };
  item_count: number;
  can_checkout: boolean;
  issues: { product_id: string; product_name: string; reason: string }[];
}

export interface CheckoutPreview {
  preview_id: string;
  cart_id: string;
  items: CartItem[];
  subtotal: { amount: number; currency: string };
  discount: { amount: number; currency: string };
  shipping: { amount: number; currency: string };
  total: { amount: number; currency: string };
  currency: string;
  payment_provider: string;
  requires_explicit_confirmation: boolean;
  expires_in_seconds: number;
}

export interface CheckoutResult {
  status: string;
  order_id: string;
  payment_id: string;
  provider: string;
  provider_order_id: string | null;
  amount: { amount: number; currency: string };
  order_status: string;
  payment_status: string;
  demo_payment_available: boolean;
}

export interface ApprovalRequestItem {
  id: string;
  campaign_id: string | null;
  action_code: string;
  payload: {
    campaign_id?: string;
    product_ids?: string[];
    discount_percent?: number;
    budget_amount?: number;
    simulation?: {
      eligible_customers: number;
      expected_conversion: number;
      expected_orders: number;
      average_order_value: number;
      expected_revenue: number;
      discount_cost: number;
      expected_incremental_revenue: number;
      roi: number | null;
      label: string;
    };
    recalculated_at?: string;
  };
  risk_level: RiskLevel;
  policy_result: { passed: boolean; violations: string[] };
  status: string;
  created_at: string | null;
  decided_at: string | null;
}
