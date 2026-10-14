import { getApiUrl, getJson, postJson } from "./client";

export type Storefront = {
  id: number;
  name: string;
  source: string;
  store_url: string;
  status: string;
};

export type AnalyticsEvent = {
  id: number;
  storefront_id: number;
  source: string;
  event_name: string;
  order_id: string | null;
  revenue: number;
  currency: string;
  occurred_at: string;
};

export type SourceBreakdown = {
  source: string;
  storefronts: number;
  events: number;
  purchases: number;
  revenue: number;
};

export type AnalyticsSummary = {
  storefronts: number;
  events: number;
  purchases: number;
  revenue: number;
  currency: string;
  by_source: SourceBreakdown[];
};

export type ProductMetric = {
  product_id: string | null;
  product_name: string;
  units_sold: number;
  revenue: number;
};

export type CustomerMetrics = {
  customers: number;
  orders: number;
  revenue: number;
  average_order_value: number;
};

export type RefundSummary = {
  refunds: number;
  refunded_amount: number;
  refund_rate: number;
};

export type PaymentMetrics = {
  attempted: number;
  succeeded: number;
  failed: number;
  success_rate: number;
  succeeded_amount: number;
  failed_amount: number;
};

export type RecoveryMetrics = {
  attempted: number;
  succeeded: number;
  recovered_amount: number;
  revenue_at_risk: number;
};

export type RevenueAtRisk = {
  open_amount: number;
  open_cases: number;
  recovered_amount: number;
  recovered_cases: number;
  lost_amount: number;
  lost_cases: number;
};

export type Transaction = {
  id: number; order_id: string | null; source: string; customer_id: string | null;
  payment_method: string | null; amount: number; currency: string; status: string; occurred_at: string;
};
export type TransactionPage = { items: Transaction[]; total: number; page: number; page_size: number };

export function fetchStorefronts(): Promise<Storefront[]> {
  return getJson<Storefront[]>("/api/commerce-sources");
}

export function connectStorefront(payload: {
  name: string;
  source: string;
  store_url: string;
}): Promise<Storefront> {
  return postJson<Storefront>("/api/commerce-sources", payload);
}

export function fetchAnalyticsSummary(): Promise<AnalyticsSummary> {
  return getJson<AnalyticsSummary>("/api/analytics/summary");
}

export function fetchAnalyticsEvents(): Promise<AnalyticsEvent[]> {
  return getJson<AnalyticsEvent[]>("/api/analytics/events");
}

export function fetchTopProducts(limit = 10): Promise<ProductMetric[]> {
  return getJson<ProductMetric[]>(`/api/analytics/top-products?limit=${limit}`);
}

export function fetchCustomerMetrics(): Promise<CustomerMetrics> {
  return getJson<CustomerMetrics>("/api/analytics/customer-metrics");
}

export function fetchRefundSummary(): Promise<RefundSummary> {
  return getJson<RefundSummary>("/api/analytics/refund-summary");
}

export function fetchPaymentMetrics(): Promise<PaymentMetrics> {
  return getJson<PaymentMetrics>("/api/analytics/payment-metrics");
}

export function fetchPaymentRecovery(): Promise<RecoveryMetrics> {
  return getJson<RecoveryMetrics>("/api/analytics/payment-recovery");
}

export function fetchRevenueAtRisk(): Promise<RevenueAtRisk> {
  return getJson<RevenueAtRisk>("/api/analytics/revenue-at-risk");
}

export function fetchTransactions(filters: { query?: string; status?: string } = {}): Promise<TransactionPage> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  return getJson<TransactionPage>(`/api/analytics/transactions?${params.toString()}`);
}

export function transactionExportUrl(): string { return `${getApiUrl()}/api/analytics/transactions/export`; }
