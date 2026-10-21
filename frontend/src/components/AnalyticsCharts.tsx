import { useMemo, useState } from "react";
import type {
  AnalyticsEvent,
  PaymentMetrics,
  ProductMetric,
  RefundSummary,
  RevenueAtRisk,
  SourceBreakdown,
} from "../api/commerce";
import type { RiskAssessmentSummary } from "../api/risk";

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

// ── 6. Statement Cash Flow Trend Chart (Dual-flow Inflow / Outflow & Net Liquidity) ─
export function StatementCashFlowChart({
  events,
  currency = "INR",
}: {
  events: AnalyticsEvent[];
  currency?: string;
}) {
  const [metric, setMetric] = useState<"volume" | "count" | "net">("volume");
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const timeline = useMemo(() => {
    const map = new Map<
      string,
      { date: string; debitVol: number; creditVol: number; debitCount: number; creditCount: number; netVol: number }
    >();

    const sorted = [...events].sort(
      (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
    );

    let running = 0;
    for (const ev of sorted) {
      const d = ev.occurred_at.slice(0, 10);
      const curr = map.get(d) ?? {
        date: d,
        debitVol: 0,
        creditVol: 0,
        debitCount: 0,
        creditCount: 0,
        netVol: 0,
      };

      if (ev.event_name === "refund") {
        curr.creditVol += ev.revenue;
        curr.creditCount += 1;
        running += ev.revenue;
      } else {
        curr.debitVol += ev.revenue;
        curr.debitCount += 1;
        running -= ev.revenue;
      }
      curr.netVol = running;
      map.set(d, curr);
    }
    return Array.from(map.values());
  }, [events]);

  const maxDebit = Math.max(...timeline.map((d) => (metric === "volume" ? d.debitVol : d.debitCount)), 10);
  const maxCredit = Math.max(...timeline.map((d) => (metric === "volume" ? d.creditVol : d.creditCount)), 10);
  const maxNet = Math.max(...timeline.map((d) => Math.abs(d.netVol)), 10);
  const maxVal = metric === "net" ? maxNet : Math.max(maxDebit, maxCredit, 10);

  const chartHeight = 200;
  const chartWidth = 540;
  const padLeft = 45;
  const padRight = 20;
  const padBottom = 30;
  const padTop = 15;
  const innerW = chartWidth - padLeft - padRight;
  const innerH = chartHeight - padTop - padBottom;

  const points = timeline.map((d, i) => {
    const x = padLeft + (timeline.length > 1 ? (i / (timeline.length - 1)) * innerW : innerW / 2);
    const debitVal = metric === "volume" ? d.debitVol : d.debitCount;
    const creditVal = metric === "volume" ? d.creditVol : d.creditCount;
    const debitY = padTop + innerH - (debitVal / maxVal) * innerH;
    const creditY = padTop + innerH - (creditVal / maxVal) * innerH;
    const netY = padTop + innerH / 2 - (d.netVol / (maxVal * 2 || 1)) * innerH;
    return { ...d, x, debitY, creditY, netY, debitVal, creditVal };
  });

  const debitLine = points.map((p) => `${p.x},${p.debitY}`).join(" ");
  const creditLine = points.map((p) => `${p.x},${p.creditY}`).join(" ");
  const netLine = points.map((p) => `${p.x},${p.netY}`).join(" ");

  const debitArea =
    points.length > 0
      ? `M ${points[0].x},${padTop + innerH} L ${points.map((p) => `${p.x},${p.debitY}`).join(" L ")} L ${
          points[points.length - 1].x
        },${padTop + innerH} Z`
      : "";

  const creditArea =
    points.length > 0
      ? `M ${points[0].x},${padTop + innerH} L ${points.map((p) => `${p.x},${p.creditY}`).join(" L ")} L ${
          points[points.length - 1].x
        },${padTop + innerH} Z`
      : "";

  const netArea =
    points.length > 0
      ? `M ${points[0].x},${padTop + innerH / 2} L ${points.map((p) => `${p.x},${p.netY}`).join(" L ")} L ${
          points[points.length - 1].x
        },${padTop + innerH / 2} Z`
      : "";

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Statement Cash Flow Trajectory</h3>
          <p className="muted">
            {metric === "net" ? (
              <span style={{ color: "#38bdf8", fontWeight: 600 }}>● Running Cumulative Cash Position</span>
            ) : (
              <>
                <span style={{ color: "#4ade80", fontWeight: 600 }}>● Deposits (Credits)</span> vs{" "}
                <span style={{ color: "#f87171", fontWeight: 600 }}>● Withdrawals (Debits)</span>
              </>
            )}
          </p>
        </div>
        <div className="chart-toggles">
          <button
            type="button"
            className={`pill-btn ${metric === "volume" ? "active" : ""}`}
            onClick={() => setMetric("volume")}
          >
            Volume ({currency})
          </button>
          <button
            type="button"
            className={`pill-btn ${metric === "count" ? "active" : ""}`}
            onClick={() => setMetric("count")}
          >
            Count (#)
          </button>
          <button
            type="button"
            className={`pill-btn ${metric === "net" ? "active" : ""}`}
            onClick={() => setMetric("net")}
          >
            Net Liquidity
          </button>
        </div>
      </div>

      {timeline.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No statement transaction activity loaded yet.
        </p>
      ) : (
        <div className="svg-chart-wrap">
          <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="timeline-svg">
            <defs>
              <linearGradient id="creditGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4ade80" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#4ade80" stopOpacity="0.0" />
              </linearGradient>
              <linearGradient id="debitGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f87171" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#f87171" stopOpacity="0.0" />
              </linearGradient>
              <linearGradient id="netGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.3" />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
              const y = padTop + innerH * (1 - ratio);
              const labelVal =
                metric === "net"
                  ? `${Math.round(maxVal * (ratio * 2 - 1))}`
                  : `${Math.round(maxVal * ratio)}`;
              return (
                <g key={ratio}>
                  <line
                    x1={padLeft}
                    y1={y}
                    x2={chartWidth - padRight}
                    y2={y}
                    stroke="#1e293b"
                    strokeDasharray="3 3"
                  />
                  <text x={padLeft - 6} y={y + 3} textAnchor="end" fontSize="9" fill="#64748b">
                    {labelVal}
                  </text>
                </g>
              );
            })}

            {metric === "net" ? (
              <>
                {netArea && <path d={netArea} fill="url(#netGrad)" />}
                {netLine && (
                  <polyline
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={netLine}
                  />
                )}
                {points.map((p, i) => (
                  <circle
                    key={p.date}
                    cx={p.x}
                    cy={p.netY}
                    r={hoveredIdx === i ? 6 : 3.5}
                    fill={hoveredIdx === i ? "#fff" : "#38bdf8"}
                    stroke="#0b1020"
                    strokeWidth="2"
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                    style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                  />
                ))}
              </>
            ) : (
              <>
                {creditArea && <path d={creditArea} fill="url(#creditGrad)" />}
                {debitArea && <path d={debitArea} fill="url(#debitGrad)" />}

                {creditLine && (
                  <polyline
                    fill="none"
                    stroke="#4ade80"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={creditLine}
                  />
                )}
                {debitLine && (
                  <polyline
                    fill="none"
                    stroke="#f87171"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={debitLine}
                  />
                )}

                {points.map((p, i) => (
                  <g
                    key={p.date}
                    onMouseEnter={() => setHoveredIdx(i)}
                    onMouseLeave={() => setHoveredIdx(null)}
                  >
                    <circle
                      cx={p.x}
                      cy={p.creditY}
                      r={hoveredIdx === i ? 6 : 3.5}
                      fill={hoveredIdx === i ? "#fff" : "#4ade80"}
                      stroke="#0b1020"
                      strokeWidth="2"
                      style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                    />
                    <circle
                      cx={p.x}
                      cy={p.debitY}
                      r={hoveredIdx === i ? 6 : 3.5}
                      fill={hoveredIdx === i ? "#fff" : "#f87171"}
                      stroke="#0b1020"
                      strokeWidth="2"
                      style={{ cursor: "pointer", transition: "r 0.15s ease" }}
                    />
                  </g>
                ))}
              </>
            )}

            {/* X-axis date labels */}
            {points.map((p, i) =>
              timeline.length <= 8 ||
              i % Math.ceil(timeline.length / 6) === 0 ||
              i === timeline.length - 1 ? (
                <text
                  key={`lbl-${p.date}`}
                  x={p.x}
                  y={padTop + innerH + 18}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#94a3b8"
                >
                  {p.date.slice(5)}
                </text>
              ) : null
            )}
          </svg>

          {hoveredIdx !== null && points[hoveredIdx] && (
            <div className="chart-tooltip">
              <strong>{points[hoveredIdx].date}</strong>
              <div style={{ color: "#4ade80" }}>
                Deposits: {currency} {points[hoveredIdx].creditVol.toFixed(2)} ({points[hoveredIdx].creditCount} txns)
              </div>
              <div style={{ color: "#f87171" }}>
                Withdrawals: {currency} {points[hoveredIdx].debitVol.toFixed(2)} ({points[hoveredIdx].debitCount} txns)
              </div>
              <div style={{ borderTop: "1px solid #334155", marginTop: "4px", paddingTop: "4px", color: "#38bdf8" }}>
                Running Balance: {currency} {points[hoveredIdx].netVol.toFixed(2)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 7. Banking Rail Failure & Volume Analysis Chart ─────────────────────────
export function BankingRailRiskChart({
  channelBreakdown = [],
  currency = "INR",
}: {
  channelBreakdown?: Array<{
    channel: string;
    total_transactions: number;
    failed_transactions: number;
    returned_transactions: number;
    failure_rate_percentage: number;
    total_volume: number;
    failed_volume: number;
  }>;
  currency?: string;
}) {
  const totalVolume = channelBreakdown.reduce((sum, c) => sum + c.total_volume, 0);
  const totalTxns = channelBreakdown.reduce((sum, c) => sum + c.total_transactions, 0);
  const maxVolume = Math.max(...channelBreakdown.map((c) => c.total_volume), 1);

  const channelColors: Record<string, string> = {
    UPI: "#8b5cf6",
    ATM: "#3b82f6",
    CARD_SWIPE: "#06b6d4",
    FEE: "#64748b",
    OTHER: "#ec4899",
    NET_BANKING: "#10b981",
  };

  // Donut circumference for r=38: 2 * Math.PI * 38 = 238.761
  const r = 38;
  const circ = 2 * Math.PI * r;
  let accumulatedRatio = 0;

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Payment Rail Reliability &amp; Failure Rates</h3>
          <p className="muted">Volume distribution and failure rates across rails</p>
        </div>
      </div>

      {channelBreakdown.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No channel metrics recorded yet. Import statements to populate rail metrics.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* SVG Donut Visual Representation */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "1.5rem",
              background: "#090d16",
              padding: "1rem",
              borderRadius: "10px",
              border: "1px solid #1e293b",
              flexWrap: "wrap",
            }}
          >
            <div style={{ position: "relative", width: "110px", height: "110px", flexShrink: 0, margin: "0 auto" }}>
              <svg viewBox="0 0 100 100" width="110" height="110" style={{ transform: "rotate(-90deg)" }}>
                <circle cx="50" cy="50" r={r} fill="transparent" stroke="#1e293b" strokeWidth="14" />
                {channelBreakdown.map((ch) => {
                  const fraction = totalVolume > 0 ? ch.total_volume / totalVolume : 0;
                  const dash = fraction * circ;
                  const offset = accumulatedRatio * circ;
                  accumulatedRatio += fraction;
                  const color = channelColors[ch.channel] ?? "#f59e0b";
                  return (
                    <circle
                      key={`donut-${ch.channel}`}
                      cx="50"
                      cy="50"
                      r={r}
                      fill="transparent"
                      stroke={color}
                      strokeWidth="14"
                      strokeDasharray={`${dash} ${circ}`}
                      strokeDashoffset={-offset}
                      style={{ transition: "stroke-dasharray 0.3s ease" }}
                    />
                  );
                })}
              </svg>
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  pointerEvents: "none",
                }}
              >
                <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "#f8fafc" }}>
                  {totalVolume >= 1000 ? `${(totalVolume / 1000).toFixed(1)}k` : totalVolume.toFixed(0)}
                </span>
                <span style={{ fontSize: "0.68rem", color: "#94a3b8" }}>{totalTxns} txns</span>
              </div>
            </div>

            {/* Donut Legend */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.5rem", flex: 1 }}>
              {channelBreakdown.map((ch) => {
                const color = channelColors[ch.channel] ?? "#f59e0b";
                const sharePct = totalVolume > 0 ? (ch.total_volume / totalVolume) * 100 : 0;
                return (
                  <div key={`legend-${ch.channel}`} style={{ display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.78rem" }}>
                    <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: color, flexShrink: 0 }} />
                    <span style={{ color: "#cbd5e1", fontWeight: 500 }}>{ch.channel.replace("_", " ")}</span>
                    <span style={{ color: "#94a3b8", marginLeft: "auto" }}>{sharePct.toFixed(1)}%</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Channel Cards with Failure & Reversal Velocity */}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {channelBreakdown.map((ch) => {
              const volPct = Math.max((ch.total_volume / maxVolume) * 100, 4);
              const isHighRisk = ch.failure_rate_percentage >= 20;
              const isElevated = ch.failure_rate_percentage >= 10 && ch.failure_rate_percentage < 20;

              const badgeColor = isHighRisk ? "#ef4444" : isElevated ? "#f59e0b" : "#10b981";
              const badgeBg = isHighRisk
                ? "rgba(239, 68, 68, 0.15)"
                : isElevated
                ? "rgba(245, 158, 11, 0.15)"
                : "rgba(16, 185, 129, 0.15)";

              return (
                <div
                  key={ch.channel}
                  style={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                    borderRadius: "8px",
                    padding: "0.75rem 1rem",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: "0.35rem",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ fontSize: "1.05rem" }}>
                        {ch.channel === "UPI"
                          ? "📱"
                          : ch.channel === "ATM"
                          ? "🏧"
                          : ch.channel === "CARD_SWIPE"
                          ? "💳"
                          : "🏦"}
                      </span>
                      <strong style={{ color: "#f8fafc", fontSize: "0.88rem" }}>{ch.channel.replace("_", " ")}</strong>
                      <span style={{ fontSize: "0.76rem", color: "#94a3b8" }}>
                        ({ch.total_transactions} txns)
                      </span>
                    </div>

                    <span
                      style={{
                        background: badgeBg,
                        color: badgeColor,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                      }}
                    >
                      {ch.failure_rate_percentage.toFixed(1)}% Decline Rate
                    </span>
                  </div>

                  <div className="progress-bg" style={{ height: "6px" }}>
                    <div
                      className="progress-fill"
                      style={{
                        width: `${volPct}%`,
                        background: `linear-gradient(90deg, #8b5cf6, #3b82f6)`,
                      }}
                    />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.78rem",
                      color: "#94a3b8",
                      marginTop: "0.35rem",
                    }}
                  >
                    <span>
                      Vol: {currency} {ch.total_volume.toFixed(2)}
                    </span>
                    <span>
                      {ch.failed_transactions} failed · {ch.returned_transactions} reversed ({currency}{" "}
                      {ch.failed_volume.toFixed(2)})
                    </span>
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

// ── 8. Statement Transaction Size Histogram ─────────────────────────────────
export function StatementTicketSizeChart({
  events = [],
  currency = "INR",
}: {
  events: AnalyticsEvent[];
  currency?: string;
}) {
  const [metric, setMetric] = useState<"count" | "volume">("count");
  const [hoveredBand, setHoveredBand] = useState<string | null>(null);

  const buckets = useMemo(() => {
    const list = [
      { label: "< 200", debits: 0, credits: 0, debitVol: 0, creditVol: 0 },
      { label: "200 - 1k", debits: 0, credits: 0, debitVol: 0, creditVol: 0 },
      { label: "1k - 3k", debits: 0, credits: 0, debitVol: 0, creditVol: 0 },
      { label: "3k - 8k", debits: 0, credits: 0, debitVol: 0, creditVol: 0 },
      { label: "8k+", debits: 0, credits: 0, debitVol: 0, creditVol: 0 },
    ];

    for (const ev of events) {
      const r = ev.revenue;
      const isCredit = ev.event_name === "refund";
      let idx = 0;
      if (r < 200) idx = 0;
      else if (r < 1000) idx = 1;
      else if (r < 3000) idx = 2;
      else if (r < 8000) idx = 3;
      else idx = 4;

      if (isCredit) {
        list[idx].credits++;
        list[idx].creditVol += r;
      } else {
        list[idx].debits++;
        list[idx].debitVol += r;
      }
    }
    return list;
  }, [events]);

  const maxVal = Math.max(
    ...buckets.map((b) =>
      metric === "count" ? Math.max(b.debits, b.credits) : Math.max(b.debitVol, b.creditVol)
    ),
    1
  );

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Transaction Ticket Size Distribution</h3>
          <p className="muted">
            <span style={{ color: "#f87171" }}>■ Debits</span> vs{" "}
            <span style={{ color: "#4ade80" }}>■ Credits</span> by denomination band
          </p>
        </div>
        <div className="chart-toggles">
          <button
            type="button"
            className={`pill-btn ${metric === "count" ? "active" : ""}`}
            onClick={() => setMetric("count")}
          >
            Count (#)
          </button>
          <button
            type="button"
            className={`pill-btn ${metric === "volume" ? "active" : ""}`}
            onClick={() => setMetric("volume")}
          >
            Volume ({currency})
          </button>
        </div>
      </div>

      <div className="histogram-grid">
        {buckets.map((b) => {
          const debitVal = metric === "count" ? b.debits : b.debitVol;
          const creditVal = metric === "count" ? b.credits : b.creditVol;
          const debitHeightPct = Math.max((debitVal / maxVal) * 100, 3);
          const creditHeightPct = Math.max((creditVal / maxVal) * 100, 3);
          const isHovered = hoveredBand === b.label;

          return (
            <div
              key={b.label}
              className="histogram-col"
              onMouseEnter={() => setHoveredBand(b.label)}
              onMouseLeave={() => setHoveredBand(null)}
              style={{
                padding: "0.5rem 0.25rem",
                borderRadius: "6px",
                background: isHovered ? "rgba(255,255,255,0.03)" : "transparent",
                transition: "background 0.15s ease",
              }}
            >
              <div style={{ display: "flex", gap: "3px", alignItems: "flex-end", height: "120px" }}>
                {/* Debit bar */}
                <div
                  style={{
                    width: "16px",
                    height: `${debitHeightPct}%`,
                    background: "linear-gradient(180deg, #f87171 0%, #dc2626 100%)",
                    borderRadius: "3px 3px 0 0",
                  }}
                  title={`Debits: ${b.debits} txns (${currency} ${b.debitVol.toFixed(2)})`}
                />
                {/* Credit bar */}
                <div
                  style={{
                    width: "16px",
                    height: `${creditHeightPct}%`,
                    background: "linear-gradient(180deg, #4ade80 0%, #16a34a 100%)",
                    borderRadius: "3px 3px 0 0",
                  }}
                  title={`Credits: ${b.credits} txns (${currency} ${b.creditVol.toFixed(2)})`}
                />
              </div>
              <span className="hist-label" style={{ fontSize: "0.74rem", fontWeight: 600 }}>
                {b.label}
              </span>
              <span style={{ fontSize: "0.68rem", color: "#94a3b8" }}>
                {metric === "count"
                  ? `${b.debits + b.credits} txns`
                  : `${currency} ${(b.debitVol + b.creditVol).toFixed(0)}`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── 9. Reversal Reconciliation & Settlement Flow Chart ──────────────────────
export function ReversalReconciliationFlowChart({
  bankRiskSummary,
  currency = "INR",
  onViewRisk,
  onImport,
}: {
  bankRiskSummary: RiskAssessmentSummary | null;
  currency?: string;
  onViewRisk?: () => void;
  onImport?: () => void;
}) {
  const total = bankRiskSummary?.total_transactions ?? 0;
  const returned = bankRiskSummary?.returned_transactions ?? 0;
  const failed = bankRiskSummary?.failed_transactions ?? 0;
  const succeeded = bankRiskSummary?.successful_transactions ?? Math.max(total - returned - failed, 0);

  const succPct = total > 0 ? (succeeded / total) * 100 : 0;
  const retPct = total > 0 ? (returned / total) * 100 : 0;
  const failPct = total > 0 ? (failed / total) * 100 : 0;

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Automated Reversal Reconciliation Flow</h3>
          <p className="muted">Dual-state RRN &amp; UTR settlement matching engine</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "0.5rem" }}>
        {/* Multi-segment Settlement Progress Bar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "#94a3b8" }}>
            <span>Settlement Breakdown · {currency} {(bankRiskSummary?.total_volume ?? 0).toFixed(2)}</span>
            <span>{total} Total Transactions</span>
          </div>
          <div
            style={{
              display: "flex",
              height: "12px",
              borderRadius: "6px",
              overflow: "hidden",
              background: "#1e293b",
            }}
          >
            {succPct > 0 && (
              <div
                style={{ width: `${succPct}%`, background: "#10b981" }}
                title={`Succeeded & Retained: ${succeeded} (${succPct.toFixed(1)}%)`}
              />
            )}
            {retPct > 0 && (
              <div
                style={{ width: `${retPct}%`, background: "#f59e0b" }}
                title={`Reconciled Reversals: ${returned} (${retPct.toFixed(1)}%)`}
              />
            )}
            {failPct > 0 && (
              <div
                style={{ width: `${failPct}%`, background: "#ef4444" }}
                title={`Failed / Unsettled: ${failed} (${failPct.toFixed(1)}%)`}
              />
            )}
          </div>
        </div>

        {/* 3 Metric Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "0.6rem 0.75rem" }}>
            <span style={{ fontSize: "0.72rem", color: "#94a3b8", display: "block" }}>Settled &amp; Paid</span>
            <strong style={{ fontSize: "1.05rem", color: "#10b981" }}>{succeeded}</strong>
            <small style={{ display: "block", color: "#64748b", fontSize: "0.68rem" }}>{succPct.toFixed(1)}%</small>
          </div>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "0.6rem 0.75rem" }}>
            <span style={{ fontSize: "0.72rem", color: "#94a3b8", display: "block" }}>Auto-Reversals</span>
            <strong style={{ fontSize: "1.05rem", color: "#f59e0b" }}>{returned}</strong>
            <small style={{ display: "block", color: "#64748b", fontSize: "0.68rem" }}>RRN matched</small>
          </div>
          <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", padding: "0.6rem 0.75rem" }}>
            <span style={{ fontSize: "0.72rem", color: "#94a3b8", display: "block" }}>Unresolved</span>
            <strong style={{ fontSize: "1.05rem", color: failed > 0 ? "#ef4444" : "#94a3b8" }}>{failed}</strong>
            <small style={{ display: "block", color: "#64748b", fontSize: "0.68rem" }}>{failPct.toFixed(1)}%</small>
          </div>
        </div>

        {/* Informative RRN Details Box */}
        <div
          style={{
            background: "#090d16",
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            border: "1px solid #1e293b",
            fontSize: "0.82rem",
            color: "#cbd5e1",
            lineHeight: 1.45,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.3rem" }}>
            <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "#10b981" }} />
            <strong style={{ color: "#60a5fa" }}>RRN &amp; UTR Reconciliation Active</strong>
          </div>
          Reversal narrations (e.g. <em>FAILED TXN REFUND</em>) are auto-paired with original debits, ensuring no double counting.
        </div>

        {/* Quick Action Buttons */}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          {onViewRisk && (
            <button
              type="button"
              onClick={onViewRisk}
              style={{
                background: "linear-gradient(90deg, #7c3aed, #db2777)",
                border: "none",
                fontSize: "0.82rem",
                padding: "0.5rem 0.85rem",
              }}
            >
              🛡️ View Risk Assessment
            </button>
          )}
          {onImport && (
            <button
              type="button"
              onClick={onImport}
              style={{ background: "#334155", border: "none", fontSize: "0.82rem", padding: "0.5rem 0.85rem" }}
            >
              📄 Import Statement
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── 10. Top Statement Counterparties & Entities Chart ───────────────────────
export function CounterpartyLeaderboardChart({
  events = [],
  currency = "INR",
}: {
  events: AnalyticsEvent[];
  currency?: string;
}) {
  const topEntities = useMemo(() => {
    const map = new Map<string, { name: string; volume: number; txns: number; debits: number; credits: number }>();
    for (const ev of events) {
      let name = "Direct Transfer";
      if (ev.order_id?.startsWith("REF-")) {
        const parts = ev.order_id.split("-");
        name = parts.length > 1 && parts[1] ? `Ref #${parts[1]}` : "Bank Transfer";
      } else if (ev.order_id?.startsWith("STMT-")) {
        name = "Statement Txn";
      } else if (ev.order_id) {
        name = ev.order_id;
      }
      const curr = map.get(name) ?? { name, volume: 0, txns: 0, debits: 0, credits: 0 };
      curr.volume += ev.revenue;
      curr.txns += 1;
      if (ev.event_name === "refund") curr.credits++;
      else curr.debits++;
      map.set(name, curr);
    }
    return Array.from(map.values())
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 5);
  }, [events]);

  const maxVol = Math.max(...topEntities.map((e) => e.volume), 1);

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Top Transacting Counterparties &amp; VPAs</h3>
          <p className="muted">Highest volume merchant and transfer endpoints</p>
        </div>
      </div>

      {topEntities.length === 0 ? (
        <p className="muted" style={{ padding: "2rem", textAlign: "center" }}>
          No counterparty entities found.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
          {topEntities.map((ent) => {
            const pct = Math.max((ent.volume / maxVol) * 100, 5);
            return (
              <div key={ent.name} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
                  <span style={{ color: "#f8fafc", fontWeight: 500 }}>{ent.name}</span>
                  <span style={{ color: "#38bdf8", fontWeight: 600 }}>
                    {currency} {ent.volume.toFixed(2)}{" "}
                    <span style={{ color: "#94a3b8", fontWeight: 400 }}>({ent.txns} txns)</span>
                  </span>
                </div>
                <div className="progress-bg" style={{ height: "6px" }}>
                  <div
                    className="progress-fill"
                    style={{
                      width: `${pct}%`,
                      background: "linear-gradient(90deg, #38bdf8, #818cf8)",
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

// ── 9. Universal Payment Funnel & Conversion Drop-off ────────────────────────
export function PaymentFunnelChart({
  paymentMetrics,
  refundSummary,
  currency = "USD",
}: {
  paymentMetrics: PaymentMetrics | null;
  refundSummary: RefundSummary | null;
  currency?: string;
}) {
  const attempted = paymentMetrics?.attempted ?? 0;
  const succeeded = paymentMetrics?.succeeded ?? 0;
  const failed = paymentMetrics?.failed ?? 0;
  const refunded = refundSummary?.refunds ?? 0;
  const netSettled = Math.max(succeeded - refunded, 0);

  const baseCount = Math.max(attempted, succeeded, 1);
  const stages = [
    {
      name: "Checkout Initiated",
      count: attempted || succeeded,
      volume: (paymentMetrics?.succeeded_amount ?? 0) + (paymentMetrics?.failed_amount ?? 0),
      color: "#38bdf8",
      pct: 100,
    },
    {
      name: "Authorization Approved",
      count: succeeded,
      volume: paymentMetrics?.succeeded_amount ?? 0,
      color: "#10b981",
      pct: baseCount > 0 ? (succeeded / baseCount) * 100 : 0,
    },
    {
      name: "Net Retained (Settled)",
      count: netSettled,
      volume: Math.max((paymentMetrics?.succeeded_amount ?? 0) - (refundSummary?.refunded_amount ?? 0), 0),
      color: "#818cf8",
      pct: baseCount > 0 ? (netSettled / baseCount) * 100 : 0,
    },
    {
      name: "Declines & Drop-offs",
      count: failed,
      volume: paymentMetrics?.failed_amount ?? 0,
      color: "#f43f5e",
      pct: baseCount > 0 ? (failed / baseCount) * 100 : 0,
    },
  ];

  return (
    <div className="panel chart-panel">
      <div className="chart-header">
        <div>
          <h3>Payment Conversion &amp; Settlement Funnel</h3>
          <p className="muted">End-to-end checkout authorization and net retention rates</p>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        {stages.map((st) => (
          <div key={st.name} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
              <span style={{ color: "#e2e8f0", fontWeight: 500 }}>{st.name}</span>
              <span style={{ color: st.color, fontWeight: 700 }}>
                {st.count} txns ({st.pct.toFixed(1)}%) · {currency} {st.volume.toFixed(2)}
              </span>
            </div>
            <div className="progress-bg" style={{ height: "8px" }}>
              <div
                className="progress-fill"
                style={{
                  width: `${Math.max(st.pct, 3)}%`,
                  backgroundColor: st.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
