import { useEffect, useState } from "react";
import {
  evaluateRealTimeRisk,
  fetchEntityRiskDNA,
  fetchRiskAssessment,
  fetchRiskEntities,
  uploadStatementFile,
  type EntityRiskDNA,
  type FailedEntitySummary,
  type RealTimeRiskEvaluationResponse,
  type RiskAssessmentSummary,
  type StatementIngestionResponse,
} from "../api/risk";

export function RiskAssessmentPanel() {
  const [summary, setSummary] = useState<RiskAssessmentSummary | null>(null);
  const [entities, setEntities] = useState<FailedEntitySummary[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Decline DNA Modal state
  const [selectedDNA, setSelectedDNA] = useState<EntityRiskDNA | null>(null);
  const [loadingDNA, setLoadingDNA] = useState<boolean>(false);

  // Network Middleware Simulator state
  const [simEntity, setSimEntity] = useState<string>("Swiggy");
  const [simChannel, setSimChannel] = useState<"ATM" | "CARD_SWIPE" | "UPI" | "ONLINE_CARD">("UPI");
  const [simAmount, setSimAmount] = useState<number>(75);
  const [simEvaluating, setSimEvaluating] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<RealTimeRiskEvaluationResponse | null>(null);

  // Statement Upload state
  const [showUploadModal, setShowUploadModal] = useState<boolean>(false);
  const [uploadFileObj, setUploadFileObj] = useState<File | null>(null);
  const [uploadPassword, setUploadPassword] = useState<string>("");
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadResult, setUploadResult] = useState<StatementIngestionResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [selectedChannel]);

  async function handleStatementUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFileObj) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const res = await uploadStatementFile(uploadFileObj, uploadPassword || undefined);
      setUploadResult(res);
      await loadData();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [sumData, entData] = await Promise.all([
        fetchRiskAssessment(selectedChannel ? { channel: selectedChannel } : undefined),
        fetchRiskEntities(selectedChannel ? { channel: selectedChannel, limit: 20 } : { limit: 20 }),
      ]);
      setSummary(sumData);
      setEntities(entData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load risk telemetry");
    } finally {
      setLoading(false);
    }
  }

  async function handleInspectDNA(entityName: string) {
    setLoadingDNA(true);
    try {
      const dna = await fetchEntityRiskDNA(entityName);
      setSelectedDNA(dna);
    } catch (err) {
      alert(`Could not load risk profile: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setLoadingDNA(false);
    }
  }

  async function handleSimulateEvaluation(e: React.FormEvent) {
    e.preventDefault();
    setSimEvaluating(true);
    try {
      const res = await evaluateRealTimeRisk({
        transaction_ref: `auth-sim-${Date.now()}`,
        entity_name: simEntity,
        channel: simChannel,
        amount: simAmount,
        currency: summary?.currency || "USD",
      });
      setSimResult(res);
    } catch (err) {
      alert(`Evaluation failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSimEvaluating(false);
    }
  }

  const tierColors: Record<string, string> = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    ELEVATED: "#eab308",
    NORMAL: "#22c55e",
  };

  const decisionColors: Record<string, string> = {
    APPROVE: "#22c55e",
    REVIEW: "#eab308",
    DECLINE: "#ef4444",
  };

  return (
    <section className="risk-panel" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header Banner */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700, color: "var(--foreground, #fff)" }}>
            Risk Assessment &amp; Decline Analytics
          </h2>
          <p style={{ margin: "0.25rem 0 0", color: "#94a3b8", fontSize: "0.9rem" }}>
            Payment decline telemetry, channel failure tracking, and merchant risk profiles.
          </p>
        </div>

        {/* Actions & Filters */}
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={() => { setShowUploadModal(true); setUploadResult(null); setUploadError(null); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.4rem 0.85rem",
              borderRadius: "8px",
              border: "1px solid rgba(59, 130, 246, 0.4)",
              background: "rgba(59, 130, 246, 0.15)",
              color: "#60a5fa",
              cursor: "pointer",
              fontSize: "0.82rem",
              fontWeight: 600,
            }}
          >
            📤 Ingest Bank Statement (CSV/Excel/PDF)
          </button>

          {/* Channel Filter Pills */}
          <div style={{ display: "flex", gap: "0.5rem", background: "rgba(255,255,255,0.05)", padding: "0.25rem", borderRadius: "8px" }}>
            {["", "ATM", "CARD_SWIPE", "UPI", "ONLINE_CARD"].map((ch) => (
              <button
                key={ch}
                type="button"
                onClick={() => setSelectedChannel(ch)}
                style={{
                  padding: "0.35rem 0.75rem",
                  borderRadius: "6px",
                  border: "none",
                  background: selectedChannel === ch ? "var(--primary, #3b82f6)" : "transparent",
                  color: selectedChannel === ch ? "#fff" : "#94a3b8",
                  cursor: "pointer",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                }}
              >
                {ch ? ch.replace("_", " ") : "All Rails"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <div style={{ padding: "1rem", background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5", borderRadius: "8px" }}>
          {error}
        </div>
      ) : null}

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Systemic Risk Score</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: summary ? tierColors[summary.risk_tier] : "#fff", marginTop: "0.25rem" }}>
            {summary ? summary.overall_risk_score : "—"}
            <span style={{ fontSize: "0.9rem", marginLeft: "0.5rem", fontWeight: 600 }}>/ 100</span>
          </div>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
            Risk Status: <strong style={{ color: summary ? tierColors[summary.risk_tier] : "#fff" }}>{summary?.risk_tier}</strong>
          </div>
        </div>

        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Failure & Reversal Rate</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: "#fff", marginTop: "0.25rem" }}>
            {summary ? `${summary.overall_failure_rate}%` : "—"}
          </div>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
            {summary?.failed_transactions ?? 0} Failed • {summary?.returned_transactions ?? 0} Returned
          </div>
        </div>

        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Total At-Risk Volume</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: "#f87171", marginTop: "0.25rem" }}>
            {summary?.currency} {summary ? summary.failed_volume.toLocaleString() : "0"}
          </div>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
            Total Processed: {summary?.currency} {summary ? summary.total_volume.toLocaleString() : "0"}
          </div>
        </div>

        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Highest Risk Rail</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#fbbf24", marginTop: "0.25rem" }}>
            {summary?.highest_risk_channel ? summary.highest_risk_channel.replace("_", " ") : "STABLE"}
          </div>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
            Top Problem Entity: <strong style={{ color: "#fff" }}>{summary?.highest_risk_entity || "None"}</strong>
          </div>
        </div>

        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Phantom Reversals (Unique)</div>
          <div style={{ fontSize: "2rem", fontWeight: 800, color: "#60a5fa", marginTop: "0.25rem" }}>
            {summary?.phantom_reversals_detected ?? 0}
          </div>
          <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" }}>
            Delayed settlement auto-reversals
          </div>
        </div>
      </div>

      {/* Main Split: Leaderboard Table on Left, Live Simulator on Right */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "1.5rem", alignItems: "start" }}>
        {/* Most Failed Transactions Leaderboard */}
        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>
                Decline &amp; Failure Rates by Merchant / Terminal
              </h3>
              <p style={{ margin: "0.2rem 0 0", color: "#94a3b8", fontSize: "0.82rem" }}>
                Ranked by failure count, returned volume, and risk index.
              </p>
            </div>
            <button
              type="button"
              onClick={loadData}
              disabled={loading}
              style={{
                background: "rgba(255,255,255,0.08)",
                border: "none",
                color: "#cbd5e1",
                padding: "0.3rem 0.75rem",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.8rem",
              }}
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8" }}>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Rank</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Entity / Merchant / ATM</th>
                  <th style={{ padding: "0.6rem 0.5rem" }}>Channel</th>
                  <th style={{ padding: "0.6rem 0.5rem", textAlign: "right" }}>Attempts</th>
                  <th style={{ padding: "0.6rem 0.5rem", textAlign: "right" }}>Failed / Rev</th>
                  <th style={{ padding: "0.6rem 0.5rem", textAlign: "right" }}>Fail Rate</th>
                  <th style={{ padding: "0.6rem 0.5rem", textAlign: "center" }}>Risk Tier</th>
                  <th style={{ padding: "0.6rem 0.5rem", textAlign: "center" }}>Risk Profile</th>
                </tr>
              </thead>
              <tbody>
                {entities.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ padding: "2rem", textAlign: "center", color: "#64748b" }}>
                      No failed transactions found for the selected rail. Everything is healthy!
                    </td>
                  </tr>
                ) : (
                  entities.map((item) => (
                    <tr
                      key={item.entity_name}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.05)",
                        transition: "background 0.2s",
                      }}
                    >
                      <td style={{ padding: "0.75rem 0.5rem", fontWeight: 700, color: "#94a3b8" }}>#{item.rank}</td>
                      <td style={{ padding: "0.75rem 0.5rem" }}>
                        <div style={{ fontWeight: 600, color: "#fff" }}>{item.entity_name}</div>
                        <div style={{ fontSize: "0.72rem", color: "#64748b", marginTop: "0.15rem" }}>
                          {item.recommendation}
                        </div>
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem" }}>
                        <span
                          style={{
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.72rem",
                            fontWeight: 600,
                            background: "rgba(59, 130, 246, 0.15)",
                            color: "#93c5fd",
                          }}
                        >
                          {item.primary_channel}
                        </span>
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>{item.total_attempts}</td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "right", color: "#f87171", fontWeight: 600 }}>
                        {item.failed_count + item.returned_count}
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "right", fontWeight: 600 }}>
                        {item.failure_rate_percentage}%
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>
                        <span
                          style={{
                            padding: "0.25rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.72rem",
                            fontWeight: 700,
                            background: `${tierColors[item.risk_tier]}22`,
                            color: tierColors[item.risk_tier],
                            border: `1px solid ${tierColors[item.risk_tier]}44`,
                          }}
                        >
                          {item.risk_tier}
                        </span>
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "center" }}>
                        <button
                          type="button"
                          onClick={() => handleInspectDNA(item.entity_name)}
                          disabled={loadingDNA}
                          style={{
                            padding: "0.25rem 0.6rem",
                            borderRadius: "4px",
                            border: "1px solid rgba(255,255,255,0.2)",
                            background: "transparent",
                            color: "#cbd5e1",
                            fontSize: "0.75rem",
                            cursor: "pointer",
                          }}
                        >
                          Inspect Profile
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Real-Time Risk Evaluation Simulator */}
        <div className="panel" style={{ padding: "1.25rem", borderRadius: "10px", background: "var(--card-bg, #1e293b)" }}>
          <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>
            Transaction Risk Evaluation Simulator
          </h3>
          <p style={{ margin: "0.25rem 0 1rem", color: "#94a3b8", fontSize: "0.82rem" }}>
            Endpoint: <code>POST /api/risk/evaluate</code>
          </p>

          <form onSubmit={handleSimulateEvaluation} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <label style={{ fontSize: "0.8rem", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              Merchant / ATM Name
              <input
                type="text"
                value={simEntity}
                onChange={(e) => setSimEntity(e.target.value)}
                required
                style={{ padding: "0.5rem", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.15)", background: "#0f172a", color: "#fff" }}
              />
            </label>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
              <label style={{ fontSize: "0.8rem", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                Payment Rail
                <select
                  value={simChannel}
                  onChange={(e) => setSimChannel(e.target.value as any)}
                  style={{ padding: "0.5rem", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.15)", background: "#0f172a", color: "#fff" }}
                >
                  <option value="UPI">UPI</option>
                  <option value="CARD_SWIPE">Card Swipe / POS</option>
                  <option value="ATM">ATM Withdrawal</option>
                  <option value="ONLINE_CARD">Online 3DS Card</option>
                </select>
              </label>

              <label style={{ fontSize: "0.8rem", color: "#cbd5e1", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                Amount ($)
                <input
                  type="number"
                  min="1"
                  value={simAmount}
                  onChange={(e) => setSimAmount(Number(e.target.value))}
                  required
                  style={{ padding: "0.5rem", borderRadius: "6px", border: "1px solid rgba(255,255,255,0.15)", background: "#0f172a", color: "#fff" }}
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={simEvaluating}
              style={{
                marginTop: "0.5rem",
                padding: "0.6rem",
                borderRadius: "6px",
                border: "none",
                background: "var(--primary, #3b82f6)",
                color: "#fff",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {simEvaluating ? "Evaluating Risk…" : "Evaluate Inbound Auth"}
            </button>
          </form>

          {/* Decision Outcome Card */}
          {simResult ? (
            <div
              style={{
                marginTop: "1rem",
                padding: "1rem",
                borderRadius: "8px",
                background: "rgba(0,0,0,0.3)",
                border: `1px solid ${decisionColors[simResult.decision]}66`,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>NETWORK DECISION</span>
                <span
                  style={{
                    padding: "0.25rem 0.6rem",
                    borderRadius: "4px",
                    fontWeight: 800,
                    fontSize: "0.85rem",
                    background: `${decisionColors[simResult.decision]}22`,
                    color: decisionColors[simResult.decision],
                    border: `1px solid ${decisionColors[simResult.decision]}`,
                  }}
                >
                  {simResult.decision}
                </span>
              </div>

              <div style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                <div>Risk Score: <strong>{simResult.risk_score} / 100</strong> ({simResult.risk_tier})</div>
                <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "0.25rem" }}>
                  Action: {simResult.suggested_action}
                </div>
              </div>

              <div style={{ marginTop: "0.5rem", fontSize: "0.72rem", color: "#64748b" }}>
                {simResult.risk_factors.map((f, i) => (
                  <div key={i}>• {f}</div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Decline DNA Modal */}
      {selectedDNA ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.75)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "1rem",
          }}
        >
          <div
            style={{
              background: "#1e293b",
              borderRadius: "12px",
              padding: "1.5rem",
              maxWidth: "600px",
              width: "100%",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.5)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "0.75rem" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "1.25rem", color: "#fff" }}>
                  Risk Profile: {selectedDNA.entity_name}
                </h3>
                <span style={{ fontSize: "0.75rem", color: "#60a5fa" }}>Cross-Rail Commerce Telemetry</span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDNA(null)}
                style={{ background: "transparent", border: "none", color: "#94a3b8", fontSize: "1.2rem", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem", fontSize: "0.85rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div style={{ background: "rgba(0,0,0,0.2)", padding: "0.75rem", borderRadius: "6px" }}>
                  <div style={{ color: "#94a3b8", fontSize: "0.72rem" }}>COMPOSITE RISK INDEX</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: tierColors[selectedDNA.risk_tier] }}>
                    {selectedDNA.composite_risk_score} <span style={{ fontSize: "0.8rem" }}>({selectedDNA.risk_tier})</span>
                  </div>
                </div>

                <div style={{ background: "rgba(0,0,0,0.2)", padding: "0.75rem", borderRadius: "6px" }}>
                  <div style={{ color: "#94a3b8", fontSize: "0.72rem" }}>CONNECTED COMMERCE ORDERS</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff" }}>
                    {selectedDNA.connected_commerce_orders_count}
                  </div>
                </div>
              </div>

              <div>
                <strong style={{ color: "#cbd5e1" }}>Rail Vulnerability Breakdown (% Failure):</strong>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.35rem" }}>
                  {Object.entries(selectedDNA.channel_vulnerabilities).map(([ch, rate]) => (
                    <span
                      key={ch}
                      style={{
                        padding: "0.25rem 0.5rem",
                        borderRadius: "4px",
                        background: "rgba(255,255,255,0.06)",
                        fontSize: "0.78rem",
                      }}
                    >
                      {ch}: <strong style={{ color: rate > 20 ? "#f87171" : "#4ade80" }}>{rate}%</strong>
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <strong style={{ color: "#cbd5e1" }}>Reversal Cadence:</strong>
                <p style={{ margin: "0.2rem 0 0", color: "#94a3b8" }}>{selectedDNA.reversal_velocity_cadence}</p>
              </div>

              <div style={{ background: "rgba(59, 130, 246, 0.1)", borderLeft: "3px solid #3b82f6", padding: "0.75rem", borderRadius: "4px" }}>
                <strong style={{ color: "#93c5fd" }}>Strategic Remediation Action:</strong>
                <p style={{ margin: "0.25rem 0 0", color: "#cbd5e1" }}>{selectedDNA.strategic_remediation}</p>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Bank Statement Upload Modal */}
      {showUploadModal ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.75)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "1rem",
          }}
        >
          <div
            style={{
              background: "#1e293b",
              borderRadius: "12px",
              padding: "1.5rem",
              maxWidth: "540px",
              width: "100%",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.5)",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "0.75rem" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "1.2rem", color: "#fff" }}>
                  🏦 Ingest Bank / Card Statement
                </h3>
                <span style={{ fontSize: "0.75rem", color: "#60a5fa" }}>Multi-Format: CSV, Excel (.xlsx/.xls), PDF</span>
              </div>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                style={{ background: "transparent", border: "none", color: "#94a3b8", fontSize: "1.2rem", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <div style={{ margin: "1rem 0", padding: "0.75rem", background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.25)", borderRadius: "6px", fontSize: "0.78rem", color: "#6ee7b7" }}>
              🔒 <strong>Privacy Protection Active:</strong> Account numbers, card numbers, Aadhaar, CVV, and mobile numbers are automatically redacted before processing.
            </div>

            {uploadError ? (
              <div style={{ margin: "0.5rem 0", padding: "0.75rem", background: "rgba(239, 68, 68, 0.2)", borderRadius: "6px", color: "#fca5a5", fontSize: "0.82rem" }}>
                {uploadError}
              </div>
            ) : null}

            {uploadResult ? (
              <div style={{ margin: "1rem 0", padding: "1rem", background: "rgba(59, 130, 246, 0.15)", borderRadius: "8px", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                <div style={{ color: "#93c5fd", fontWeight: 700, fontSize: "0.95rem" }}>
                  ✅ Statement Ingestion Completed ({uploadResult.format_detected})
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.75rem", fontSize: "0.82rem", color: "#cbd5e1" }}>
                  <div>Rows Ingested: <strong>{uploadResult.rows_ingested}</strong> / {uploadResult.rows_parsed}</div>
                  <div>Reversals Linked: <strong style={{ color: "#38bdf8" }}>{uploadResult.reversals_linked}</strong></div>
                  <div>Total Debits: <strong>₹{uploadResult.total_debit_amount}</strong></div>
                  <div>Total Credits: <strong>₹{uploadResult.total_credit_amount}</strong></div>
                </div>
                {uploadResult.errors.length > 0 ? (
                  <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#f87171" }}>
                    Warnings: {uploadResult.errors.join(", ")}
                  </div>
                ) : null}
              </div>
            ) : null}

            <form onSubmit={handleStatementUpload} style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.82rem", color: "#cbd5e1", marginBottom: "0.35rem", fontWeight: 600 }}>
                  Select Statement File (.csv, .xlsx, .xls, .pdf)
                </label>
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls,.pdf"
                  required
                  onChange={(e) => setUploadFileObj(e.target.files?.[0] || null)}
                  style={{
                    width: "100%",
                    padding: "0.5rem",
                    borderRadius: "6px",
                    background: "rgba(0,0,0,0.3)",
                    border: "1px solid rgba(255,255,255,0.15)",
                    color: "#fff",
                    fontSize: "0.82rem",
                  }}
                />
              </div>

              {uploadFileObj?.name.toLowerCase().endsWith(".pdf") ? (
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", color: "#cbd5e1", marginBottom: "0.35rem", fontWeight: 600 }}>
                    PDF Password (Optional — if password-protected by bank)
                  </label>
                  <input
                    type="password"
                    placeholder="e.g. DOB or mobile number"
                    value={uploadPassword}
                    onChange={(e) => setUploadPassword(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "0.5rem",
                      borderRadius: "6px",
                      background: "rgba(0,0,0,0.3)",
                      border: "1px solid rgba(255,255,255,0.15)",
                      color: "#fff",
                      fontSize: "0.82rem",
                    }}
                  />
                </div>
              ) : null}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: "6px",
                    background: "transparent",
                    border: "1px solid rgba(255,255,255,0.2)",
                    color: "#94a3b8",
                    cursor: "pointer",
                    fontSize: "0.85rem",
                  }}
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFileObj}
                  style={{
                    padding: "0.5rem 1.25rem",
                    borderRadius: "6px",
                    background: "var(--primary, #3b82f6)",
                    border: "none",
                    color: "#fff",
                    fontWeight: 600,
                    cursor: uploading ? "wait" : "pointer",
                    fontSize: "0.85rem",
                    opacity: uploading || !uploadFileObj ? 0.6 : 1,
                  }}
                >
                  {uploading ? "Ingesting & Linking Reversals..." : "Ingest & Reconcile"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}
