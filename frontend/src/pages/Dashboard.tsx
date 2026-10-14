import { useEffect, useState, type FormEvent } from "react";
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
} from "../components/AnalyticsCharts";

type View = "overview" | "transactions" | "integrations" | "import";

export function Dashboard({ session, onLogout }: { session: MeResponse; onLogout: () => void }) {
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
  } = useCommerce();

  const [view, setView] = useState<View>("overview");
  const [name, setName] = useState("");
  const [source, setSource] = useState("");
  const [storeUrl, setStoreUrl] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [transactionTotal, setTransactionTotal] = useState(0);

  useEffect(() => {
    if (view === "transactions") {
      void fetchTransactions({ query, status }).then((data) => {
        setTransactions(data.items);
        setTransactionTotal(data.total);
      });
    }
  }, [view, query, status]);

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
          <span>Analytics MCP</span>
        </h1>
        {(
          [
            ["overview", "Dashboard"],
            ["transactions", "Transactions"],
            ["integrations", "Integrations"],
            ["import", "Import Studio"],
          ] as const
        ).map(([id, label]) => (
          <button
            className={view === id ? "nav active" : "nav"}
            key={id}
            onClick={() => setView(id)}
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
                ? "Commerce & Payment Analytics"
                : view === "transactions"
                  ? "Transactions Explorer"
                  : view === "integrations"
                    ? "Integrations Overview"
                    : "Schema & Data Type Import Studio"}
            </h1>
            <p className="lede">
              {session.organization.name} · {session.user.email}
            </p>
          </div>
          <button onClick={onLogout}>Sign out</button>
        </header>

        {view === "overview" && (
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

            {/* ── Level 3 Graphs: Payment Lifecycle / Risk & Sources Status ── */}
            <section className="two-column">
              <PaymentRecoveryWidget
                paymentMetrics={paymentMetrics}
                revenueAtRisk={revenueAtRisk}
                refundSummary={refundSummary}
                currency={currency}
              />
              <div className="panel chart-panel">
                <div className="chart-header">
                  <div>
                    <h3>Integration Monitors</h3>
                    <p className="muted">Live status of connected data sources</p>
                  </div>
                </div>
                {storefronts.length ? (
                  <div className="integration-list-box">
                    {storefronts.map((store) => (
                      <p className="integration-row" key={store.id}>
                        <span className="dot" />
                        <strong>{store.name}</strong>
                        <small>{store.source} · {store.status}</small>
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="muted" style={{ padding: "1.5rem", textAlign: "center" }}>
                    No sources connected yet.
                  </p>
                )}
              </div>
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

        {view === "import" && (
          <ImportWizard storefronts={storefronts} onImported={() => void reload()} />
        )}

        {view === "transactions" && (
          <section className="panel">
            <div className="section-title">
              <div>
                <h2>All transactions</h2>
                <p className="muted">{transactionTotal} matching transactions</p>
              </div>
              <a className="button-link" href={transactionExportUrl()}>
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
