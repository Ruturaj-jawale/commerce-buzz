"""Analytics API schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CommerceEventIngest(BaseModel):
    event_name: str | None = Field(default=None, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload_size(self) -> "CommerceEventIngest":
        import json
        from app.core.config import get_settings
        if len(json.dumps(self.payload, separators=(",", ":")).encode("utf-8")) > get_settings().max_ingestion_payload_bytes:
            raise ValueError("payload exceeds the configured maximum size")
        if len(self.payload.get("items", [])) > 1000:
            raise ValueError("payload items cannot exceed 1,000")
        return self


class AnalyticsEventRead(BaseModel):
    id: int
    storefront_id: int
    source: str = Field(validation_alias="provider")
    event_name: str
    order_id: str | None
    revenue: float
    currency: str
    occurred_at: datetime

    model_config = {"from_attributes": True}


class SourceBreakdown(BaseModel):
    source: str
    storefronts: int
    events: int
    purchases: int
    revenue: float


class AnalyticsSummary(BaseModel):
    storefronts: int
    events: int
    purchases: int
    revenue: float
    currency: str = "USD"
    by_source: list[SourceBreakdown]


class DateRange(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    def validate_range(self) -> None:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")


class ProductMetric(BaseModel):
    product_id: str | None
    product_name: str
    units_sold: int
    revenue: float


class CustomerMetrics(BaseModel):
    customers: int
    orders: int
    revenue: float
    average_order_value: float


class RefundSummary(BaseModel):
    refunds: int
    refunded_amount: float
    refund_rate: float


class PaymentMetrics(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    success_rate: float
    succeeded_amount: float
    failed_amount: float


class RecoveryMetrics(BaseModel):
    attempted: int
    succeeded: int
    recovered_amount: float
    revenue_at_risk: float


class TransactionEvent(BaseModel):
    id: int
    event_name: str
    order_id: str | None
    revenue: float
    occurred_at: datetime


class TransactionRead(BaseModel):
    """Provider-neutral transaction row for the dashboard and MCP consumers."""
    id: int
    order_id: str | None
    source: str
    customer_id: str | None = None
    payment_method: str | None = None
    amount: float
    currency: str
    status: str
    occurred_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionRead]
    total: int
    page: int
    page_size: int


class IngestionJobRead(BaseModel):
    id: int
    storefront_id: int
    status: str
    attempts: int
    event_id: int | None
    error_message: str | None
    error_code: str | None
    created_at: datetime
    processed_at: datetime | None

    model_config = {"from_attributes": True}
