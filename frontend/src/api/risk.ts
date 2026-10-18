import { getJson, postJson, uploadFile } from "./client";
import { sanitizeStatementFileBeforeUpload } from "../utils/sanitizer";

export interface ChannelRiskMetrics {
  channel: string;
  total_transactions: number;
  failed_transactions: number;
  returned_transactions: number;
  failure_rate_percentage: number;
  total_volume: number;
  failed_volume: number;
}

export interface FailedEntitySummary {
  rank: number;
  entity_name: string;
  primary_channel: string;
  total_attempts: number;
  failed_count: number;
  returned_count: number;
  total_amount: number;
  failed_amount: number;
  failure_rate_percentage: number;
  risk_score: number;
  risk_tier: "NORMAL" | "ELEVATED" | "HIGH" | "CRITICAL";
  phantom_reversal_risk: number;
  recommendation: string;
}

export interface RiskAssessmentSummary {
  total_transactions: number;
  total_volume: number;
  successful_transactions: number;
  failed_transactions: number;
  returned_transactions: number;
  failed_volume: number;
  overall_failure_rate: number;
  overall_risk_score: number;
  risk_tier: "NORMAL" | "ELEVATED" | "HIGH" | "CRITICAL";
  highest_risk_channel: string;
  highest_risk_entity: string | null;
  channel_breakdown: Array<{
    channel: string;
    total_transactions: number;
    failed_transactions: number;
    returned_transactions: number;
    failure_rate_percentage: number;
    total_volume: number;
    failed_volume: number;
  }>;
  phantom_reversals_detected: number;
  currency: string;
}

export interface RealTimeRiskEvaluationRequest {
  transaction_ref: string;
  entity_name: string;
  channel?: "ATM" | "CARD_SWIPE" | "UPI" | "ONLINE_CARD" | "TRANSFER";
  amount: number;
  currency?: string;
  card_bin?: string;
  country_code?: string;
}

export interface RealTimeRiskEvaluationResponse {
  transaction_ref: string;
  decision: "APPROVE" | "REVIEW" | "DECLINE";
  risk_score: number;
  risk_tier: "NORMAL" | "ELEVATED" | "HIGH" | "CRITICAL";
  channel: string;
  entity_name: string;
  historical_entity_failure_rate: number;
  risk_factors: string[];
  suggested_action: string;
  evaluated_at: string;
}

export interface EntityRiskDNA {
  entity_name: string;
  profile_status: string;
  composite_risk_score: number;
  risk_tier: "NORMAL" | "ELEVATED" | "HIGH" | "CRITICAL";
  channel_vulnerabilities: Record<string, number>;
  reversal_velocity_cadence: string;
  predicted_loss_ratio: number;
  connected_commerce_orders_count: number;
  strategic_remediation: string;
}

export function fetchRiskAssessment(params?: { channel?: string }): Promise<RiskAssessmentSummary> {
  const query = params?.channel ? `?channel=${encodeURIComponent(params.channel)}` : "";
  return getJson<RiskAssessmentSummary>(`/api/analytics/risk-assessment${query}`);
}

export function fetchRiskEntities(params?: { limit?: number; channel?: string }): Promise<FailedEntitySummary[]> {
  const parts: string[] = [];
  if (params?.limit) parts.push(`limit=${params.limit}`);
  if (params?.channel) parts.push(`channel=${encodeURIComponent(params.channel)}`);
  const query = parts.length ? `?${parts.join("&")}` : "";
  return getJson<FailedEntitySummary[]>(`/api/analytics/risk-entities${query}`);
}

export function fetchEntityRiskDNA(entityName: string): Promise<EntityRiskDNA> {
  return getJson<EntityRiskDNA>(`/api/analytics/risk-dna/${encodeURIComponent(entityName)}`);
}

export function evaluateRealTimeRisk(
  payload: RealTimeRiskEvaluationRequest
): Promise<RealTimeRiskEvaluationResponse> {
  return postJson<RealTimeRiskEvaluationResponse>("/api/risk/evaluate", payload);
}

export interface SystemLensProfile {
  detected_mode: "COMMERCE" | "BANK_NETWORK" | "HYBRID";
  confidence_score: number;
  recommended_lens: "COMMERCE" | "BANK_NETWORK";
  rationale: string;
  total_bank_transactions: number;
  total_commerce_orders: number;
  active_banking_rails: string[];
  has_reversals: boolean;
  has_storefronts: boolean;
}

export function fetchSystemLens(): Promise<SystemLensProfile> {
  return getJson<SystemLensProfile>("/api/analytics/system-lens");
}

export interface StatementIngestionResponse {
  filename: string;
  format_detected: string;
  rows_parsed: number;
  rows_ingested: number;
  rows_skipped: number;
  reversals_linked: number;
  total_debit_amount: number;
  total_credit_amount: number;
  errors: string[];
}

export async function uploadStatementFile(
  file: File,
  password?: string,
  bankPreset?: string,
  customHeaders?: Record<string, string>
): Promise<StatementIngestionResponse> {
  const { file: safeFile } = await sanitizeStatementFileBeforeUpload(file);
  const fields: Record<string, string> = {};
  if (password) fields.password = password;
  if (bankPreset && bankPreset !== "auto") fields.bank_preset = bankPreset;
  if (customHeaders && Object.keys(customHeaders).length > 0) {
    fields.custom_headers = JSON.stringify(customHeaders);
  }
  return uploadFile<StatementIngestionResponse>("/api/analytics/statements/upload", safeFile, fields);
}

