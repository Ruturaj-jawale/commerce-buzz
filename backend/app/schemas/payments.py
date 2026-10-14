"""Schemas for the universal payment and revenue-recovery model."""

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class PaymentFailureRead(BaseModel):
    attempt_id: int
    order_ref: str
    payment_ref: str
    customer_id: str | None
    attempt_no: int
    amount: float
    currency: str
    failure_code: str | None
    failure_reason: str | None
    recovery_status: str | None
    occurred_at: datetime


class RevenueAtRisk(BaseModel):
    open_amount: float
    open_cases: int
    recovered_amount: float
    recovered_cases: int
    lost_amount: float
    lost_cases: int
    currency: str = "USD"


class RevenueMetrics(BaseModel):
    gross: float
    refunds: float
    chargebacks: float
    fees: float
    net: float
    currency: str = "USD"


class OrderMetricsRead(BaseModel):
    orders: int
    revenue: float
    average_order_value: float


class PaymentHistoryEntry(BaseModel):
    kind: str
    status: str
    order_ref: str
    amount: float
    currency: str
    occurred_at: datetime


class DateRangeInput(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "DateRangeInput":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self
