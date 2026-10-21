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

export function fetchAnalyticsSummary(source?: string): Promise<AnalyticsSummary> {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJson<AnalyticsSummary>(`/api/analytics/summary${q}`);
}

export function fetchAnalyticsEvents(source?: string, limit = 250): Promise<AnalyticsEvent[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (source) params.set("source", source);
  return getJson<AnalyticsEvent[]>(`/api/analytics/events?${params.toString()}`);
}

export function fetchTopProducts(limit = 10, source?: string): Promise<ProductMetric[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (source) params.set("source", source);
  return getJson<ProductMetric[]>(`/api/analytics/top-products?${params.toString()}`);
}

export function fetchCustomerMetrics(source?: string): Promise<CustomerMetrics> {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJson<CustomerMetrics>(`/api/analytics/customer-metrics${q}`);
}

export function fetchRefundSummary(source?: string): Promise<RefundSummary> {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJson<RefundSummary>(`/api/analytics/refund-summary${q}`);
}

export function fetchPaymentMetrics(source?: string): Promise<PaymentMetrics> {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJson<PaymentMetrics>(`/api/analytics/payment-metrics${q}`);
}

export function fetchPaymentRecovery(source?: string): Promise<RecoveryMetrics> {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return getJson<RecoveryMetrics>(`/api/analytics/payment-recovery${q}`);
}

export function fetchRevenueAtRisk(): Promise<RevenueAtRisk> {
  return getJson<RevenueAtRisk>("/api/analytics/revenue-at-risk");
}

export function fetchTransactions(filters: { query?: string; status?: string; source?: string } = {}): Promise<TransactionPage> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  return getJson<TransactionPage>(`/api/analytics/transactions?${params.toString()}`);
}

export function transactionExportUrl(source?: string): string {
  const q = source ? `?source=${encodeURIComponent(source)}` : "";
  return `${getApiUrl()}/api/analytics/transactions/export${q}`;
}
