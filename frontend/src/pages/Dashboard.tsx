import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { MeResponse } from "../api/auth";
import { StatusCard } from "../components/StatusCard";
import { fetchTransactions, transactionExportUrl, type Transaction } from "../api/commerce";
import { useCommerce } from "../hooks/useCommerce";
import { ImportWizard } from "./ImportWizard";
import {
  RevenueTimelineChart,
  TopProductsChart,
  ChannelBreakdownChart,
  OrderDistributionChart,
  PaymentRecoveryWidget,
  StatementCashFlowChart,
  BankingRailRiskChart,
  StatementTicketSizeChart,
  PaymentFunnelChart,
  ReversalReconciliationFlowChart,
  CounterpartyLeaderboardChart,
} from "../components/AnalyticsCharts";
import { RiskAssessmentPanel } from "../components/RiskAssessmentPanel";
import {
  fetchSystemLens,
  fetchRiskAssessment,
  type SystemLensProfile,
  type RiskAssessmentSummary,
} from "../api/risk";

type View = "overview" | "transactions" | "risk" | "integrations" | "import";

export function Dashboard({ session, onLogout }: { session: MeResponse; onLogout: () => void }) {
  const [view, setView] = useState<View>("overview");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [storeUrl, setStoreUrl] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [transactionTotal, setTransactionTotal] = useState(0);

  // Smart Adaptive Persona Lens (Commerce vs Banking & Statements)
  const [systemLens, setSystemLens] = useState<SystemLensProfile | null>(null);
  const [userLensMode, setUserLensMode] = useState<"auto" | "COMMERCE" | "BANK_NETWORK">("auto");
  const [bankRiskSummary, setBankRiskSummary] = useState<RiskAssessmentSummary | null>(null);

  const activeLens =
    userLensMode === "auto"
      ? (systemLens?.recommended_lens ?? "COMMERCE")
      : userLensMode;

  // Derive source filter: Commerce lens = exclude bank data, Bank lens = only bank data
  const dataSource = activeLens === "BANK_NETWORK" ? "bank-statement" : "commerce";

  const {
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
  } = useCommerce(dataSource);

  const refreshRiskAndLens = useCallback(() => {
    void fetchSystemLens().then(setSystemLens).catch(() => {});
    void fetchRiskAssessment().then(setBankRiskSummary).catch(() => {});
  }, []);

  const loadTransactions = useCallback(() => {
    void fetchTransactions({ query, status, source: dataSource }).then((data) => {
      setTransactions(data.items);
      setTransactionTotal(data.total);
    }).catch(() => {});
  }, [query, status, dataSource]);

  const handleImported = useCallback(async () => {
    await reload();
    refreshRiskAndLens();
    loadTransactions();
  }, [reload, refreshRiskAndLens, loadTransactions]);

  useEffect(() => {
    refreshRiskAndLens();
  }, [refreshRiskAndLens, view, userLensMode, activeLens]);

  useEffect(() => {
    if (activeLens === "COMMERCE" && view === "risk") {
      setView("overview");
    }
    if (activeLens === "BANK_NETWORK" && view === "integrations") {
      setView("overview");
    }
  }, [activeLens, view]);

  useEffect(() => {
    if (view === "transactions") {
      loadTransactions();
    }
  }, [view, loadTransactions]);

  const aov = summary?.purchases ? summary.revenue / summary.purchases : 0;
  const currency = summary?.currency ?? "USD";
  const successPct = paymentMetrics ? (paymentMetrics.success_rate * 100).toFixed(0) : "100";

  async function submit(event: FormEvent) {
    event.preventDefault();
    await connect(name, source, storeUrl);
    setName("");
    setSource("");
    setStoreUrl("");
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <h1>
          Commerce<br />
          <span style={{ color: activeLens === "BANK_NETWORK" ? "#c084fc" : "#60a5fa" }}>
            {activeLens === "BANK_NETWORK" ? "Statement Analytics" : "Analytics MCP"}
          </span>
        </h1>
        {[
          ["overview", "Dashboard"],
          ["transactions", "Transactions"],
          ...(activeLens === "BANK_NETWORK" ? [["risk", "Risk Assessment"] as const] : []),
          ...(activeLens === "COMMERCE" ? [["integrations", "Integrations"] as const] : []),
          ["import", "Import Studio"],
        ].map(([id, label]) => (
          <button
            className={view === id ? "nav active" : "nav"}
            key={id}
            onClick={() => setView(id as View)}
          >
            {label}
          </button>
        ))}
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>
              {view === "overview"
                ? activeLens === "BANK_NETWORK"
                  ? "Banking & Statement Analytics"
                  : "Commerce & Payment Analytics"
                : view === "transactions"
                  ? "Transactions"
                  : view === "risk"
                    ? "Risk & Decline Analytics"
                    : view === "integrations"
                      ? "Commerce Integrations"
                      : "Data Import Studio"}
            </h1>
            <p className="lede">
              {session.organization.name} · {session.user.email}
            </p>
          </div>
          <button onClick={onLogout}>Sign out</button>
        </header>

        {/* Adaptive Surveillance Persona Switcher */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "linear-gradient(90deg, #0f172a 0%, #1e293b 100%)",
            padding: "0.65rem 1.25rem",
            borderRadius: "10px",
            marginBottom: "1.5rem",
            border: "1px solid #334155",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <span
              style={{
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "#94a3b8",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              Active Perspective:
            </span>
            <div
              style={{
                display: "inline-flex",
                background: "#090d16",
                borderRadius: "8px",
                padding: "3px",
                border: "1px solid #1e293b",
              }}
            >
              <button
                type="button"
                onClick={() => setUserLensMode("auto")}
                style={{
                  background:
                    userLensMode === "auto"
                      ? "linear-gradient(90deg, #2563eb, #7c3aed)"
                      : "transparent",
                  color: userLensMode === "auto" ? "#ffffff" : "#94a3b8",
                  border: "none",
                  padding: "0.4rem 0.8rem",
                  borderRadius: "6px",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                ✨ Auto-Detect{" "}
                {systemLens
                  ? `(${systemLens.detected_mode === "BANK_NETWORK" ? "Bank Statements" : "Commerce"})`
                  : ""}
              </button>
              <button
                type="button"
                onClick={() => setUserLensMode("COMMERCE")}
                style={{
                  background:
                    userLensMode === "COMMERCE"
                      ? "linear-gradient(90deg, #2563eb, #0284c7)"
                      : "transparent",
                  color: userLensMode === "COMMERCE" ? "#ffffff" : "#94a3b8",
                  border: "none",
                  padding: "0.4rem 0.8rem",
                  borderRadius: "6px",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                🛒 Commerce Analytics
              </button>
              <button
                type="button"
                onClick={() => setUserLensMode("BANK_NETWORK")}
                style={{
                  background:
                    userLensMode === "BANK_NETWORK"
                      ? "linear-gradient(90deg, #7c3aed, #db2777)"
                      : "transparent",
                  color: userLensMode === "BANK_NETWORK" ? "#ffffff" : "#94a3b8",
                  border: "none",
                  padding: "0.4rem 0.8rem",
                  borderRadius: "6px",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                🏦 Banking &amp; Statements
              </button>
            </div>
          </div>

          {systemLens && (
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <span
                style={{
                  fontSize: "0.78rem",
                  background:
                    systemLens.detected_mode === "BANK_NETWORK"
                      ? "rgba(124, 58, 237, 0.15)"
                      : "rgba(37, 99, 235, 0.15)",
                  color: systemLens.detected_mode === "BANK_NETWORK" ? "#c084fc" : "#93c5fd",
                  padding: "0.3rem 0.75rem",
                  borderRadius: "999px",
                  border: "1px solid rgba(255,255,255,0.08)",
                  fontWeight: 500,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    width: "7px",
                    height: "7px",
                    borderRadius: "50%",
                    background:
                      systemLens.detected_mode === "BANK_NETWORK" ? "#a855f7" : "#3b82f6",
                  }}
                />
                {systemLens.rationale}
              </span>
            </div>
          )}
        </div>

        {view === "overview" && activeLens === "BANK_NETWORK" && (
          <>
            <p className="lede">
              Statement transaction monitoring, payment channel failure tracking, and automated reversal reconciliation.
            </p>

            {/* ── 6 Banking Status Cards ── */}
            <section className="grid kpis">
              <StatusCard
                label="Statement Volume"
                value={`${bankRiskSummary?.currency ?? currency} ${(bankRiskSummary?.total_volume ?? 0).toFixed(2)}`}
              />
              <StatusCard
                label="Total Transactions"
                value={String(bankRiskSummary?.total_transactions ?? 0)}
              />
              <StatusCard
                label="Failure Rate"
                value={`${(bankRiskSummary?.overall_failure_rate ?? 0).toFixed(1)}%`}
              />
              <StatusCard
                label="Failed Transactions"
                value={String(bankRiskSummary?.failed_transactions ?? 0)}
              />
              <StatusCard
                label="Reconciled Reversals"
                value={String(bankRiskSummary?.returned_transactions ?? 0)}
              />
              <StatusCard
                label="Risk Tier"
                value={bankRiskSummary?.risk_tier ?? "NORMAL"}
              />
            </section>

            {/* ── Level 1 Bank Widgets: Statement Cash Flow & Rail Performance ── */}
            <section className="two-column">
              <StatementCashFlowChart
                events={events}
                currency={bankRiskSummary?.currency ?? currency}
              />
              <BankingRailRiskChart
                channelBreakdown={bankRiskSummary?.channel_breakdown ?? []}
                currency={bankRiskSummary?.currency ?? currency}
              />
            </section>

            {/* ── Level 2 Bank Widgets: Denomination Ticket Breakdown & Reversal Engine ── */}
            <section className="two-column">
              <StatementTicketSizeChart
                events={events}
                currency={bankRiskSummary?.currency ?? currency}
              />
              <ReversalReconciliationFlowChart
                bankRiskSummary={bankRiskSummary}
                currency={bankRiskSummary?.currency ?? currency}
                onViewRisk={() => setView("risk")}
                onImport={() => setView("import")}
              />
            </section>

            {/* ── Level 3 Bank Widgets: Top Counterparties & Zero-Trust Audit ── */}
            <section className="two-column">
              <CounterpartyLeaderboardChart
                events={events}
                currency={bankRiskSummary?.currency ?? currency}
              />
              <div className="panel chart-panel">
                <div className="chart-header">
                  <div>
                    <h3>Zero-Trust Data Governance &amp; Audit</h3>
                    <p className="muted">Dual-entry balance verification &amp; PII/PCI security</p>
                  </div>
                </div>
                <div style={{ display: "grid", gap: "0.85rem", marginTop: "1rem" }}>
                  <div
                    style={{
                      background: "#0f172a",
                      padding: "0.85rem 1rem",
                      borderRadius: "8px",
                      border: "1px solid #1e293b",
                    }}
                  >
                    <h4 style={{ margin: "0 0 0.35rem 0", color: "#38bdf8", fontSize: "0.88rem" }}>
                      🛡️ Client-Side PII/PCI Sanitization
                    </h4>
                    <p style={{ margin: 0, fontSize: "0.82rem", color: "#cbd5e1", lineHeight: 1.45 }}>
                      Account numbers, card PANs, and contact details are redacted before ingestion, ensuring full compliance with payment security standards.
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                    <button
                      type="button"
                      onClick={() => setView("transactions")}
                      style={{
                        background: "#1e293b",
                        border: "1px solid #334155",
                        color: "#f8fafc",
                        fontSize: "0.82rem",
                        padding: "0.5rem 0.85rem",
                      }}
                    >
                      💳 View All Statement Transactions →
                    </button>
                    <button
                      type="button"
                      onClick={() => setView("risk")}
                      style={{
                        background: "rgba(124, 58, 237, 0.2)",
                        border: "1px solid #7c3aed",
                        color: "#c084fc",
                        fontSize: "0.82rem",
                        padding: "0.5rem 0.85rem",
                      }}
                    >
                      ⚡ Risk &amp; Decline Sentinel
                    </button>
                  </div>
                </div>
              </div>
            </section>
          </>
        )}

        {view === "overview" && activeLens === "COMMERCE" && (
          <>
            <p className="lede">
              Universal, provider-neutral commerce analytics shared by the dashboard and MCP tools.
            </p>

            {/* ── 6 KPI Cards ── */}
            <section className="grid kpis">
              <StatusCard
                label="Gross Revenue"
                value={`${currency} ${(summary?.revenue ?? 0).toFixed(2)}`}
              />
              <StatusCard
                label="Total Transactions"
                value={String(summary?.purchases ?? 0)}
              />
              <StatusCard
                label="Avg Order Value"
                value={`${currency} ${aov.toFixed(2)}`}
              />
              <StatusCard
                label="Unique Customers"
                value={String(customerMetrics?.customers ?? summary?.purchases ?? 0)}
              />
              <StatusCard
                label="Payment Success Rate"
                value={`${successPct}%`}
              />
              <StatusCard
                label="Revenue at Risk"
                value={`${currency} ${(revenueAtRisk?.open_amount ?? 0).toFixed(2)}`}
              />
            </section>

            {/* ── Level 1 Graphs: Timeline & Channel Breakdown ── */}
            <section className="two-column">
              <RevenueTimelineChart events={events} currency={currency} />
              <ChannelBreakdownChart sources={summary?.by_source ?? []} currency={currency} />
            </section>

            {/* ── Level 2 Graphs: Top Products & Order Distribution ── */}
            <section className="two-column">
              <TopProductsChart products={topProducts} currency={currency} />
              <OrderDistributionChart events={events} currency={currency} />
            </section>

            {/* ── Level 3 Graphs: Payment Lifecycle / Risk & Funnel ── */}
            <section className="two-column">
              <PaymentRecoveryWidget
                paymentMetrics={paymentMetrics}
                revenueAtRisk={revenueAtRisk}
                refundSummary={refundSummary}
                currency={currency}
              />
              <PaymentFunnelChart
                paymentMetrics={paymentMetrics}
                refundSummary={refundSummary}
                currency={currency}
              />
            </section>

            {/* ── Level 4: Connected Systems & Integration Monitors ── */}
            <section className="panel chart-panel">
              <div className="chart-header">
                <div>
                  <h3>Integration Monitors</h3>
                  <p className="muted">Live status of connected commerce data sources and ingestion endpoints</p>
                </div>
              </div>
              {storefronts.length ? (
                <div className="integration-list-box" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "0.75rem" }}>
                  {storefronts.map((store) => (
                    <div
                      key={store.id}
                      style={{
                        background: "#0f172a",
                        border: "1px solid #1e293b",
                        borderRadius: "8px",
                        padding: "0.75rem 1rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.6rem",
                      }}
                    >
                      <span className="dot" style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
                      <div>
                        <strong style={{ display: "block", fontSize: "0.88rem", color: "#f8fafc" }}>{store.name}</strong>
                        <small style={{ color: "#94a3b8", fontSize: "0.75rem" }}>{store.source} · {store.status}</small>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted" style={{ padding: "1.5rem", textAlign: "center" }}>
                  No sources connected yet.
                </p>
              )}
            </section>
          </>
        )}

        {view === "integrations" && (
          <>
            <section className="panel">
              <h2>Connect a universal data source</h2>
              <p className="muted">
                Add any commerce platform, warehouse, webhook, or custom REST source. Credentials are
                never stored in the browser; provider OAuth/API-key flows belong to optional
                ingestion adapters.
              </p>
              <form className="form" onSubmit={(event) => void submit(event)}>
                <label>
                  Name
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Source label
                  <input
                    placeholder="Custom REST, storefront, warehouse…"
                    value={source}
                    onChange={(event) => setSource(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Source URL
                  <input
                    value={storeUrl}
                    onChange={(event) => setStoreUrl(event.target.value)}
                    required
                  />
                </label>
                <button disabled={busy}>Register source</button>
              </form>
              {error && <p className="error">{error}</p>}
            </section>
            <section className="panel">
              <h2>Integration monitors</h2>
              {storefronts.length ? (
                <ul className="list">
                  {storefronts.map((store) => (
                    <li key={store.id}>
                      <strong>{store.name}</strong>
                      <span>
                        {store.source} · {store.status}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No sources yet.</p>
              )}
            </section>
          </>
        )}

        {view === "risk" && activeLens === "BANK_NETWORK" && (
          <RiskAssessmentPanel />
        )}

        {view === "import" && (
          <ImportWizard
            storefronts={storefronts}
            onImported={handleImported}
            onViewTransactions={() => setView("transactions")}
            initialMode={activeLens === "BANK_NETWORK" ? "bank_statement" : "commerce"}
          />
        )}

        {view === "transactions" && (
          <section className="panel">
            <div className="section-title">
              <div>
                <h2>All transactions</h2>
                <p className="muted">{transactionTotal} matching transactions</p>
              </div>
              <a className="button-link" href={transactionExportUrl(dataSource)}>
                Export CSV
              </a>
            </div>
            <div className="filters">
              <input
                placeholder="Search order, customer, amount"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <select value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="">All statuses</option>
                <option value="succeeded">Succeeded</option>
                <option value="refunded">Refunded</option>
                <option value="failed">Failed</option>
                <option value="pending">Pending</option>
              </select>
            </div>
            {transactions.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Date</th>
                    <th>Customer</th>
                    <th>Source</th>
                    <th>Amount</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((item) => (
                    <tr key={item.id}>
                      <td>{item.order_id ?? item.id}</td>
                      <td>{new Date(item.occurred_at).toLocaleString()}</td>
                      <td>{item.customer_id ?? "—"}</td>
                      <td>{item.source}</td>
                      <td>
                        {item.currency} {item.amount.toFixed(2)}
                      </td>
                      <td>
                        <span className={`badge ${item.status}`}>{item.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>No matching transactions.</p>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
