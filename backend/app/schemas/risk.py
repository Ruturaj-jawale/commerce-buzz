"""Schemas for Card Network, ATM, UPI Risk Assessment, and Cross-Rail Decline DNA."""

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

RiskTier = Literal["NORMAL", "ELEVATED", "HIGH", "CRITICAL"]
RiskDecision = Literal["APPROVE", "REVIEW", "DECLINE"]
TransactionChannelType = Literal[
    "ATM",
    "CARD_SWIPE",
    "UPI",
    "ONLINE_CARD",
    "TRANSFER",
    "FEE",
    "OTHER",
]


class ChannelRiskMetrics(BaseModel):
    channel: str
    total_transactions: int
    failed_transactions: int
    returned_transactions: int
    failure_rate_percentage: float
    total_volume: float
    failed_volume: float


class FailedEntitySummary(BaseModel):
    rank: int
    entity_name: str
    primary_channel: str
    total_attempts: int
    failed_count: int
    returned_count: int
    total_amount: float
    failed_amount: float
    failure_rate_percentage: float
    risk_score: float = Field(description="Composite risk index between 0 and 100")
    risk_tier: RiskTier
    phantom_reversal_risk: float = Field(default=0.0, description="Predicted probability of delayed ghost reversal (0.0 to 1.0)")
    recommendation: str


class RiskAssessmentSummary(BaseModel):
    total_transactions: int
    total_volume: float
    successful_transactions: int
    failed_transactions: int
    returned_transactions: int
    failed_volume: float
    overall_failure_rate: float
    overall_risk_score: float
    risk_tier: RiskTier
    highest_risk_channel: str
    highest_risk_entity: str | None
    channel_breakdown: list[ChannelRiskMetrics]
    phantom_reversals_detected: int
    currency: str = "USD"


# Real-time Card Network Middleware: Mastercard / Visa -> SaaS MCP Risk -> Bank
class RealTimeRiskEvaluationRequest(BaseModel):
    transaction_ref: str = Field(min_length=2, max_length=120)
    card_bin: str | None = Field(default=None, max_length=8, description="First 6-8 digits of card")
    entity_name: str = Field(min_length=1, max_length=180, description="Merchant, ATM terminal ID, or VPA")
    channel: TransactionChannelType = Field(default="CARD_SWIPE")
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", max_length=8)
    country_code: str | None = Field(default=None, max_length=3)
    raw_narration: str | None = Field(default=None)


class RealTimeRiskEvaluationResponse(BaseModel):
    transaction_ref: str
    decision: RiskDecision
    risk_score: float = Field(description="Calculated risk index (0 to 100)")
    risk_tier: RiskTier
    channel: str
    entity_name: str
    historical_entity_failure_rate: float
    risk_factors: list[str]
    suggested_action: str
    evaluated_at: datetime


# Innovative Cross-Rail Decline DNA: Merchant / Terminal Behavioral Fingerprint
class EntityRiskDNA(BaseModel):
    entity_name: str
    profile_status: str
    composite_risk_score: float
    risk_tier: RiskTier
    channel_vulnerabilities: dict[str, float] = Field(
        description="Failure rate breakdown per rail (ATM vs UPI vs Card Swipe)"
    )
    reversal_velocity_cadence: str = Field(
        description="Cadence behavior: e.g. Immediate switch reversal vs 48-72h settlement lag"
    )
    predicted_loss_ratio: float
    connected_commerce_orders_count: int = Field(
        description="Number of verified commerce line-item orders cross-correlated with switch records"
    )
    strategic_remediation: str


# Smart Persona Lens Auto-Detection: Commerce vs Bank / Card Network Switch
SystemPersonaMode = Literal["COMMERCE", "BANK_NETWORK", "HYBRID"]


class SystemLensProfile(BaseModel):
    detected_mode: SystemPersonaMode = Field(description="Auto-detected operational persona")
    confidence_score: float = Field(description="Confidence score between 0.0 and 1.0")
    recommended_lens: Literal["COMMERCE", "BANK_NETWORK"] = Field(description="Default dashboard view to render")
    rationale: str = Field(description="Detailed explanation of the auto-detection rationale")
    total_bank_transactions: int = Field(description="Transactions identified as ATM, UPI, Card Swipe, or statement narrations")
    total_commerce_orders: int = Field(description="E-commerce store orders and cart checkout events")
    active_banking_rails: list[str] = Field(description="Active detected channels (e.g. ATM, UPI, CARD_SWIPE)")
    has_reversals: bool = Field(description="Whether explicit reversal / return links are present")
    has_storefronts: bool = Field(description="Whether connected storefront integrations exist")


# Multi-Format Bank Statement Ingestion Result
class StatementIngestionResponse(BaseModel):
    filename: str
    format_detected: str
    rows_parsed: int
    rows_ingested: int
    rows_skipped: int
    reversals_linked: int
    total_debit_amount: float
    total_credit_amount: float
    errors: list[str] = Field(default_factory=list)

