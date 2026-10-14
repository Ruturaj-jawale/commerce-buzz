import { useMemo, useState } from "react";
import type {
  AnalyticsEvent,
  PaymentMetrics,
  ProductMetric,
  RefundSummary,
  RevenueAtRisk,
  SourceBreakdown,
} from "../api/commerce";

// ── 1. Revenue & Orders Timeline Chart ──────────────────────────────────────
export function RevenueTimelineChart({
  events,
  currency = "USD",
}: {
  events: AnalyticsEvent[];
  currency?: string;
}) {
  const [metric, setMetric] = useState<"revenue" | "orders">("revenue");
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Group events by date (YYYY-MM-DD)
  const timeline = useMemo(() => {
    const map = new Map<string, { date: string; revenue: number; orders: number }>();
    // Sort oldest first
    const sorted = [...events].sort(
      (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
    );

    for (const ev of sorted) {
      if (ev.event_name !== "purchase") continue;
      const d = ev.occurred_at.slice(0, 10);
      const curr = map.get(d) ?? { date: d, revenue: 0, orders: 0 };
      curr.revenue += ev.revenue;
      curr.orders += 1;
      map.set(d, curr);
    }
    return Array.from(map.values());
  }, [events]);

  const maxRevenue = Math.max(...timeline.map((d) => d.revenue), 10);
  const maxOrders = Math.max(...timeline.map((d) => d.orders), 1);
  const maxVal = metric === "revenue" ? maxRevenue : maxOrders;

  const chartHeight = 180;
  const chartWidth = 540;
  const padLeft = 40;
  const padRight = 20;
  const padBottom = 30;
  const padTop = 15;
  const innerW = chartWidth - padLeft - padRight;
  const innerH = chartHeight - padTop - padBottom;

  const points = timeline.map((d, i) => {
    const x = padLeft + (timeline.length > 1 ? (i / (timeline.length - 1)) * innerW : innerW / 2);
    const val = metric === "revenue" ? d.revenue : d.orders;
    const y = padTop + innerH - (val / maxVal) * innerH;
    return { ...d, x, y, val };
  });

  const polylineStr = points.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPath =
    points.length > 0
      ? `M ${points[0].x},${padTop + innerH} L ${points.map((p) => `${p.x},${p.y}`).join(" L ")} L ${
          points[points.length - 1].x
        },${padTop + innerH} Z`
      : "";

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Revenue &amp; Activity Timeline</h3>
          <p className="muted">Daily aggregated purchase trends</p>
        </div>
        <div className="chart-toggles">
          <button
            type="button"
            className={`pill-btn ${metric === "revenue" ? "active" : ""}`}
            onClick={() => setMetric("revenue")}
          >
            Revenue ($)
          </button>
          <button
            type="button"
            className={`pill-btn ${metric === "orders" ? "active" : ""}`}
            onClick={() => setMetric("orders")}
          >
            Orders (#)
          </button>
        </div>
      </div>

      {timeline.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No purchase activity recorded yet.
        </p>
      ) : (
        <div className="svg-chart-wrap">
          <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="timeline-svg">
            <defs>
              <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.4" />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
              const y = padTop + innerH * (1 - ratio);
              const labelVal = metric === "revenue" ? `$${Math.round(maxVal * ratio)}` : Math.round(maxVal * ratio);
              return (
                <g key={ratio}>
                  <line x1={padLeft} y1={y} x2={chartWidth - padRight} y2={y} stroke="#1e293b" strokeDasharray="3 3" />
                  <text x={padLeft - 6} y={y + 3} textAnchor="end" fontSize="9" fill="#64748b">
                    {labelVal}
                  </text>
                </g>
              );
            })}

            {/* Area Fill */}
            {areaPath && <path d={areaPath} fill="url(#revGrad)" />}

            {/* Trend Polyline */}
            {polylineStr && (
              <polyline
                fill="none"
                stroke="#38bdf8"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={polylineStr}
              />
            )}

            {/* Data Dots & X Axis Labels */}
            {points.map((p, i) => (
              <g key={p.date} onMouseEnter={() => setHoveredIdx(i)} onMouseLeave={() => setHoveredIdx(null)}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={hoveredIdx === i ? 6 : 3.5}
                  fill={hoveredIdx === i ? "#fff" : "#38bdf8"}
                  stroke="#0b1020"
                  strokeWidth="2"
                  style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                />
                {(timeline.length <= 8 || i % Math.ceil(timeline.length / 6) === 0 || i === timeline.length - 1) && (
                  <text x={p.x} y={padTop + innerH + 18} textAnchor="middle" fontSize="9" fill="#94a3b8">
                    {p.date.slice(5)}
                  </text>
                )}
              </g>
            ))}
          </svg>

          {/* Interactive Tooltip Overlay */}
          {hoveredIdx !== null && points[hoveredIdx] && (
            <div className="chart-tooltip">
              <strong>{points[hoveredIdx].date}</strong>
              <div>Revenue: {currency} {points[hoveredIdx].revenue.toFixed(2)}</div>
              <div>Orders: {points[hoveredIdx].orders}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 2. Top Products Ranked Bar Chart ───────────────────────────────────────
export function TopProductsChart({
  products,
  currency = "USD",
}: {
  products: ProductMetric[];
  currency?: string;
}) {
  const maxRevenue = Math.max(...products.map((p) => p.revenue), 1);

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Top Selling Products</h3>
          <p className="muted">Ranked by gross sales volume</p>
        </div>
      </div>
      {products.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No itemized product data available.
        </p>
      ) : (
        <div className="product-bars-list">
          {products.slice(0, 6).map((prod, idx) => {
            const pct = Math.max((prod.revenue / maxRevenue) * 100, 3);
            return (
              <div key={prod.product_id || prod.product_name} className="product-bar-row">
                <div className="product-bar-meta">
                  <span className="prod-rank">#{idx + 1}</span>
                  <span className="prod-name" title={prod.product_name}>
                    {prod.product_name}
                  </span>
                  <span className="prod-units">{prod.units_sold} sold</span>
                  <span className="prod-rev">
                    {currency} {prod.revenue.toFixed(2)}
                  </span>
                </div>
                <div className="progress-bg">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${pct}%`,
                      background: `linear-gradient(90deg, #38bdf8, #818cf8)`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── 3. Revenue by Channel / Source Chart ────────────────────────────────────
const CHANNEL_COLORS = ["#38bdf8", "#818cf8", "#34d399", "#f59e0b", "#f43f5e"];

export function ChannelBreakdownChart({
  sources,
  currency = "USD",
}: {
  sources: SourceBreakdown[];
  currency?: string;
}) {
  const totalRev = sources.reduce((acc, s) => acc + s.revenue, 0) || 1;

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Channel &amp; Source Distribution</h3>
          <p className="muted">Revenue contribution by data source</p>
        </div>
      </div>
      {sources.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No connected sources.
        </p>
      ) : (
        <div className="channel-breakdown">
          {/* Segmented bar */}
          <div className="stacked-bar">
            {sources.map((src, i) => {
              const widthPct = (src.revenue / totalRev) * 100;
              return (
                <div
                  key={src.source}
                  style={{
                    width: `${Math.max(widthPct, 2)}%`,
                    backgroundColor: CHANNEL_COLORS[i % CHANNEL_COLORS.length],
                  }}
                  title={`${src.source}: ${currency} ${src.revenue.toFixed(2)} (${widthPct.toFixed(1)}%)`}
                />
              );
            })}
          </div>

          {/* Breakdown cards */}
          <div className="source-legend-grid">
            {sources.map((src, i) => {
              const share = ((src.revenue / totalRev) * 100).toFixed(1);
              return (
                <div key={src.source} className="source-legend-item">
                  <div className="source-legend-header">
                    <span
                      className="legend-dot"
                      style={{ backgroundColor: CHANNEL_COLORS[i % CHANNEL_COLORS.length] }}
                    />
                    <strong>{src.source}</strong>
                    <span className="source-share">{share}%</span>
                  </div>
                  <div className="source-legend-vals">
                    <span>
                      {currency} {src.revenue.toFixed(2)}
                    </span>
                    <small className="muted">{src.purchases} orders</small>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 4. Order Ticket Value Histogram ─────────────────────────────────────────
export function OrderDistributionChart({
  events,
  currency = "USD",
}: {
  events: AnalyticsEvent[];
  currency?: string;
}) {
  const buckets = useMemo(() => {
    const list = [
      { label: "< $25", count: 0, revenue: 0 },
      { label: "$25 - $50", count: 0, revenue: 0 },
      { label: "$50 - $75", count: 0, revenue: 0 },
      { label: "$75 - $100", count: 0, revenue: 0 },
      { label: "$100+", count: 0, revenue: 0 },
    ];
    for (const ev of events) {
      if (ev.event_name !== "purchase") continue;
      const r = ev.revenue;
      if (r < 25) {
        list[0].count++;
        list[0].revenue += r;
      } else if (r < 50) {
        list[1].count++;
        list[1].revenue += r;
      } else if (r < 75) {
        list[2].count++;
        list[2].revenue += r;
      } else if (r < 100) {
        list[3].count++;
        list[3].revenue += r;
      } else {
        list[4].count++;
        list[4].revenue += r;
      }
    }
    return list;
  }, [events]);

  const maxCount = Math.max(...buckets.map((b) => b.count), 1);

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Order Value Distribution</h3>
          <p className="muted">Transaction volume by ticket size bucket</p>
        </div>
      </div>
      <div className="histogram-grid">
        {buckets.map((b) => {
          const heightPct = Math.max((b.count / maxCount) * 100, 4);
          return (
            <div key={b.label} className="histogram-col">
              <span className="hist-count">{b.count}</span>
              <div className="hist-bar-track">
                <div
                  className="hist-bar-fill"
                  style={{
                    height: `${heightPct}%`,
                    background: "linear-gradient(180deg, #38bdf8, #2563eb)",
                  }}
                  title={`${b.count} orders (${currency} ${b.revenue.toFixed(2)})`}
                />
              </div>
              <span className="hist-label">{b.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 5. Payment Health & Revenue Recovery Widget ─────────────────────────────
export function PaymentRecoveryWidget({
  paymentMetrics,
  revenueAtRisk,
  refundSummary,
  currency = "USD",
}: {
  paymentMetrics: PaymentMetrics | null;
  revenueAtRisk: RevenueAtRisk | null;
  refundSummary: RefundSummary | null;
  currency?: string;
}) {
  const successRate = paymentMetrics ? (paymentMetrics.success_rate * 100).toFixed(1) : "100.0";
  const attempted = paymentMetrics?.attempted ?? 0;
  const succeeded = paymentMetrics?.succeeded ?? 0;
  const failed = paymentMetrics?.failed ?? 0;
  const atRisk = revenueAtRisk?.open_amount ?? 0;
  const recovered = revenueAtRisk?.recovered_amount ?? 0;
  const refundRate = refundSummary ? (refundSummary.refund_rate * 100).toFixed(1) : "0.0";

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Payment Health &amp; Revenue Recovery</h3>
          <p className="muted">Universal payment lifecycle &amp; risk funnel</p>
        </div>
        <span className="badge succeeded">{successRate}% Success</span>
      </div>

      <div className="recovery-kpi-grid">
        <div className="recovery-stat-box">
          <span className="rec-label">Attempts Succeeded</span>
          <strong className="rec-val text-green">
            {succeeded} / {attempted || succeeded}
          </strong>
          <small className="muted">{currency} {(paymentMetrics?.succeeded_amount ?? 0).toFixed(2)} captured</small>
        </div>

        <div className="recovery-stat-box">
          <span className="rec-label">Payment Failures</span>
          <strong className="rec-val text-red">{failed}</strong>
          <small className="muted">{currency} {(paymentMetrics?.failed_amount ?? 0).toFixed(2)} failed</small>
        </div>

        <div className="recovery-stat-box">
          <span className="rec-label">Revenue at Risk</span>
          <strong className="rec-val text-amber">{currency} {atRisk.toFixed(2)}</strong>
          <small className="muted">{revenueAtRisk?.open_cases ?? 0} open cases</small>
        </div>

        <div className="recovery-stat-box">
          <span className="rec-label">Recovered Revenue</span>
          <strong className="rec-val text-cyan">{currency} {recovered.toFixed(2)}</strong>
          <small className="muted">{revenueAtRisk?.recovered_cases ?? 0} cases recovered</small>
        </div>

        <div className="recovery-stat-box">
          <span className="rec-label">Refund Rate</span>
          <strong className="rec-val text-purple">{refundRate}%</strong>
          <small className="muted">{refundSummary?.refunds ?? 0} refunded orders</small>
        </div>
      </div>
    </div>
  );
}
