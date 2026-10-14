import { useCallback, useEffect, useState } from "react";
import {
  connectStorefront,
  fetchAnalyticsEvents,
  fetchAnalyticsSummary,
  fetchCustomerMetrics,
  fetchPaymentMetrics,
  fetchRefundSummary,
  fetchRevenueAtRisk,
  fetchStorefronts,
  fetchTopProducts,
  type AnalyticsEvent,
  type AnalyticsSummary,
  type CustomerMetrics,
  type PaymentMetrics,
  type ProductMetric,
  type RefundSummary,
  type RevenueAtRisk,
  type Storefront,
} from "../api/commerce";

export function useCommerce() {
  const [storefronts, setStorefronts] = useState<Storefront[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [events, setEvents] = useState<AnalyticsEvent[]>([]);
  const [topProducts, setTopProducts] = useState<ProductMetric[]>([]);
  const [customerMetrics, setCustomerMetrics] = useState<CustomerMetrics | null>(null);
  const [refundSummary, setRefundSummary] = useState<RefundSummary | null>(null);
  const [paymentMetrics, setPaymentMetrics] = useState<PaymentMetrics | null>(null);
  const [revenueAtRisk, setRevenueAtRisk] = useState<RevenueAtRisk | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [
        nextStores,
        nextSummary,
        nextEvents,
        nextProducts,
        nextCustomers,
        nextRefunds,
        nextPayments,
        nextRisk,
      ] = await Promise.all([
        fetchStorefronts().catch(() => []),
        fetchAnalyticsSummary().catch(() => null),
        fetchAnalyticsEvents().catch(() => []),
        fetchTopProducts(8).catch(() => []),
        fetchCustomerMetrics().catch(() => null),
        fetchRefundSummary().catch(() => null),
        fetchPaymentMetrics().catch(() => null),
        fetchRevenueAtRisk().catch(() => null),
      ]);
      setStorefronts(nextStores);
      setSummary(nextSummary);
      setEvents(nextEvents);
      setTopProducts(nextProducts);
      setCustomerMetrics(nextCustomers);
      setRefundSummary(nextRefunds);
      setPaymentMetrics(nextPayments);
      setRevenueAtRisk(nextRisk);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    }
  }, []);

  useEffect(() => {
    void reload().catch((err: Error) => setError(err.message));
  }, [reload]);

  async function connect(name: string, source: string, storeUrl: string) {
    setBusy(true);
    setError(null);
    try {
      await connectStorefront({ name, source, store_url: storeUrl });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect storefront");
    } finally {
      setBusy(false);
    }
  }

  return {
    storefronts,
    summary,
    events,
    topProducts,
    customerMetrics,
    refundSummary,
    paymentMetrics,
    revenueAtRisk,
    error,
    busy,
    connect,
    reload,
  };
}
