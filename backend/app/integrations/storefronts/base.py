"""Platform-neutral canonical commerce-event contract."""

from dataclasses import dataclass, field
from typing import Any


CANONICAL_EVENTS = (
    "product_viewed",
    "add_to_cart",
    "checkout_started",
    "purchase",
    "refund",
    "order_created",
    "payment_attempted",
    "payment_failed",
    "payment_succeeded",
    "payment_captured",
    "payment_settled",
    "refund_created",
    "chargeback_created",
    "recovery_attempted",
    "recovery_succeeded",
)


@dataclass
class CanonicalCommerceEvent:
    event_name: str
    order_id: str | None = None
    revenue: float = 0.0
    currency: str = "USD"
    properties: dict[str, Any] = field(default_factory=dict)


class UniversalCommerceAdapter:
    """Accept the public canonical event shape from any commerce system."""

    def normalize(self, payload: dict[str, Any], event_name: str | None = None) -> CanonicalCommerceEvent:
        name = event_name or payload.get("event_name")
        if name not in CANONICAL_EVENTS:
            supported = ", ".join(CANONICAL_EVENTS)
            raise ValueError(f"event_name must be one of: {supported}")
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise ValueError("items must be a list")
        idempotency_key = str(payload.get("idempotency_key") or "").strip() or None
        if not idempotency_key and payload.get("order_id"):
            idempotency_key = f"{name}:{payload.get('order_id')}"
        return CanonicalCommerceEvent(
            event_name=name,
            order_id=str(payload.get("order_id") or "") or None,
            revenue=float(payload.get("revenue") or 0),
            currency=str(payload.get("currency") or "USD"),
            properties={
                "customer_id": str(payload.get("customer_id") or "") or None,
                "items": items,
                "metadata": payload.get("metadata") or {},
                "idempotency_key": idempotency_key,
            },
        )
