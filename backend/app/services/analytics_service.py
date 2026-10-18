"""First-party analytics platform: ingest normalized commerce events and summarize them."""

import json
from collections import defaultdict
from datetime import date, datetime, time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalyticsEvent, Organization, Storefront
from app.integrations.storefronts.registry import get_adapter
from app.schemas.analytics import (
    AnalyticsEventRead,
    AnalyticsSummary,
    CommerceEventIngest,
    CustomerMetrics,
    PaymentMetrics,
    ProductMetric,
    RecoveryMetrics,
    SourceBreakdown,
    RefundSummary,
    TransactionEvent,
    TransactionPage,
    TransactionRead,
)
from app.services.payment_service import PaymentService
from app.services.storefront_service import StorefrontService


class AnalyticsService:
    def __init__(self, storefronts: StorefrontService | None = None, payments: PaymentService | None = None) -> None:
        self._storefronts = storefronts or StorefrontService()
        self._payments = payments or PaymentService()

    def ingest(self, db: Session, organization: Organization, storefront_id: int, body: CommerceEventIngest) -> AnalyticsEventRead:
        storefront = self._storefronts.get(db, organization, storefront_id)
        adapter = get_adapter()
        try:
            canonical = adapter.normalize(body.payload, body.event_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if canonical.currency != "USD":
            raise HTTPException(status_code=422, detail="Only USD is accepted until currency normalization is implemented")
        idempotency_key = canonical.properties.get("idempotency_key")
        if idempotency_key:
            existing = db.scalar(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.organization_id == organization.id,
                    AnalyticsEvent.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return AnalyticsEventRead.model_validate(existing)
        event = AnalyticsEvent(
            organization_id=organization.id,
            storefront_id=storefront.id,
            provider=storefront.provider,
            event_name=canonical.event_name,
            order_id=canonical.order_id,
            revenue=canonical.revenue,
            currency=canonical.currency,
            properties_json=json.dumps(canonical.properties),
            idempotency_key=idempotency_key,
            occurred_at=datetime.utcnow(),
        )
        self._payments.land_event(db, organization, storefront, canonical)
        db.add(event)
        db.commit()
        db.refresh(event)
        return AnalyticsEventRead.model_validate(event)

    def ingest_sample_purchase(self, db: Session, organization: Organization, storefront_id: int) -> AnalyticsEventRead:
        storefront = self._storefronts.get(db, organization, storefront_id)
        payload = {"order_id": f"demo-{storefront.id}", "revenue": 42.0, "currency": "USD", "customer_id": "demo-customer", "items": [{"product_id": "demo-product", "name": "Demo product", "price": 42.0, "quantity": 1}]}
        return self.ingest(db, organization, storefront_id, CommerceEventIngest(payload=payload, event_name="purchase"))

    def list_events(self, db: Session, organization: Organization, limit: int = 25, source: str | None = None) -> list[AnalyticsEventRead]:
        stmt = select(AnalyticsEvent).where(AnalyticsEvent.organization_id == organization.id)
        if source == "bank-statement":
            stmt = stmt.where(AnalyticsEvent.provider == "bank-statement")
        elif source == "commerce":
            stmt = stmt.where(AnalyticsEvent.provider != "bank-statement")
        elif source:
            stmt = stmt.where(AnalyticsEvent.provider == source)
        rows = db.scalars(stmt.order_by(AnalyticsEvent.id.desc()).limit(limit)).all()
        return [AnalyticsEventRead.model_validate(row) for row in rows]

    def _events_for_range(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> list[AnalyticsEvent]:
        statement = select(AnalyticsEvent).where(AnalyticsEvent.organization_id == organization.id)
        if start_date:
            statement = statement.where(AnalyticsEvent.occurred_at >= datetime.combine(start_date, time.min))
        if end_date:
            statement = statement.where(AnalyticsEvent.occurred_at <= datetime.combine(end_date, time.max))
        if source == "bank-statement":
            statement = statement.where(AnalyticsEvent.provider == "bank-statement")
        elif source == "commerce":
            statement = statement.where(AnalyticsEvent.provider != "bank-statement")
        elif source:
            statement = statement.where(AnalyticsEvent.provider == source)
        return list(db.scalars(statement).all())

    def summary(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> AnalyticsSummary:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
        stmt_sf = select(Storefront).where(Storefront.organization_id == organization.id)
        if source == "bank-statement":
            stmt_sf = stmt_sf.where(Storefront.provider == "bank-statement")
        elif source == "commerce":
            stmt_sf = stmt_sf.where(Storefront.provider != "bank-statement")
        elif source:
            stmt_sf = stmt_sf.where(Storefront.provider == source)
        storefronts = db.scalars(stmt_sf).all()
        events = self._events_for_range(db, organization, start_date, end_date, source=source)
        grouped: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"storefronts": 0, "events": 0, "purchases": 0, "revenue": 0.0}
        )
        for store in storefronts:
            grouped[store.provider]["storefronts"] += 1
        purchases = 0
        revenue = 0.0
        for event in events:
            grouped[event.provider]["events"] += 1
            if event.event_name == "purchase":
                grouped[event.provider]["purchases"] += 1
                grouped[event.provider]["revenue"] += event.revenue
                purchases += 1
                revenue += event.revenue
        breakdown = [
            SourceBreakdown(
                source=provider,
                storefronts=int(stats["storefronts"]),
                events=int(stats["events"]),
                purchases=int(stats["purchases"]),
                revenue=round(float(stats["revenue"]), 2),
            )
            for provider, stats in sorted(grouped.items())
        ]
        return AnalyticsSummary(
            storefronts=len(storefronts),
            events=len(events),
            purchases=purchases,
            revenue=round(revenue, 2),
            by_source=breakdown,
        )

    def top_products(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, limit: int = 10, source: str | None = None) -> list[ProductMetric]:
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
        totals: dict[tuple[str | None, str], dict[str, float | int]] = defaultdict(lambda: {"units_sold": 0, "revenue": 0.0})
        for event in self._events_for_range(db, organization, start_date, end_date, source=source):
            if event.event_name != "purchase":
                continue
            properties = json.loads(event.properties_json)
            items = properties.get("items") or []
            for item in items:
                product_id = item.get("product_id") or item.get("productId") or item.get("id")
                product_name = str(item.get("title") or item.get("name") or item.get("product_name") or "Unknown product")
                quantity = int(item.get("quantity") or 1)
                line_total = float(item.get("price") or item.get("line_price") or item.get("total") or 0) * quantity
                bucket = totals[(str(product_id) if product_id is not None else None, product_name)]
                bucket["units_sold"] += quantity
                bucket["revenue"] += line_total
        return [
            ProductMetric(product_id=product_id, product_name=name, units_sold=int(values["units_sold"]), revenue=round(float(values["revenue"]), 2))
            for (product_id, name), values in sorted(totals.items(), key=lambda item: float(item[1]["revenue"]), reverse=True)[:limit]
        ]

    def customer_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> CustomerMetrics:
        purchases = [event for event in self._events_for_range(db, organization, start_date, end_date, source=source) if event.event_name == "purchase"]
        customer_ids = {
            str(json.loads(event.properties_json).get("customer_id"))
            for event in purchases
            if json.loads(event.properties_json).get("customer_id")
        }
        revenue = round(sum(event.revenue for event in purchases), 2)
        return CustomerMetrics(customers=len(customer_ids), orders=len(purchases), revenue=revenue, average_order_value=round(revenue / len(purchases), 2) if purchases else 0.0)

    def refund_summary(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> RefundSummary:
        events = self._events_for_range(db, organization, start_date, end_date, source=source)
        purchases = [event for event in events if event.event_name == "purchase"]
        refunds = [event for event in events if event.event_name == "refund"]
        refunded_amount = round(sum(event.revenue for event in refunds), 2)
        return RefundSummary(refunds=len(refunds), refunded_amount=refunded_amount, refund_rate=round(len(refunds) / len(purchases), 4) if purchases else 0.0)

    def payment_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> PaymentMetrics:
        events = self._events_for_range(db, organization, start_date, end_date, source=source)
        attempted = [event for event in events if event.event_name == "payment_attempted"]
        succeeded = [event for event in events if event.event_name in {"payment_succeeded", "purchase"}]
        failed = [event for event in events if event.event_name == "payment_failed"]
        succeeded_amount = round(sum(event.revenue for event in succeeded), 2)
        failed_amount = round(sum(event.revenue for event in failed), 2)
        attempts = len(attempted) or (len(succeeded) + len(failed))
        return PaymentMetrics(
            attempted=attempts,
            succeeded=len(succeeded),
            failed=len(failed),
            success_rate=round(len(succeeded) / attempts, 4) if attempts else 0.0,
            succeeded_amount=succeeded_amount,
            failed_amount=failed_amount,
        )

    def payment_recovery(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> RecoveryMetrics:
        events = self._events_for_range(db, organization, start_date, end_date, source=source)
        attempted = [event for event in events if event.event_name == "recovery_attempted"]
        succeeded = [event for event in events if event.event_name == "recovery_succeeded"]
        failed = [event for event in events if event.event_name == "payment_failed"]
        recovered_amount = round(sum(event.revenue for event in succeeded), 2)
        recovered_orders = {event.order_id for event in succeeded if event.order_id}
        at_risk = round(sum(event.revenue for event in failed if event.order_id not in recovered_orders), 2)
        return RecoveryMetrics(
            attempted=len(attempted),
            succeeded=len(succeeded),
            recovered_amount=recovered_amount,
            revenue_at_risk=at_risk,
        )

    def customer_payment_history(self, db: Session, organization: Organization, customer_id: str) -> list[TransactionEvent]:
        rows = []
        for event in self._events_for_range(db, organization):
            properties = json.loads(event.properties_json)
            if str(properties.get("customer_id") or "") == customer_id:
                rows.append(event)
        return [
            TransactionEvent(id=event.id, event_name=event.event_name, order_id=event.order_id, revenue=event.revenue, occurred_at=event.occurred_at)
            for event in rows
        ]

    def transaction_lifecycle(self, db: Session, organization: Organization, order_id: str) -> list[TransactionEvent]:
        rows = db.scalars(
            select(AnalyticsEvent)
            .where(AnalyticsEvent.organization_id == organization.id, AnalyticsEvent.order_id == order_id)
            .order_by(AnalyticsEvent.occurred_at, AnalyticsEvent.id)
        ).all()
        return [
            TransactionEvent(id=event.id, event_name=event.event_name, order_id=event.order_id, revenue=event.revenue, occurred_at=event.occurred_at)
            for event in rows
        ]

    def transactions(
        self, db: Session, organization: Organization, query: str | None = None, status: str | None = None,
        currency: str | None = None, source: str | None = None, page: int = 1, page_size: int = 25,
    ) -> TransactionPage:
        """Return presentation rows from normalized events without exposing SQL or raw payloads."""
        stmt = select(AnalyticsEvent).where(AnalyticsEvent.organization_id == organization.id)
        if source == "bank-statement":
            stmt = stmt.where(AnalyticsEvent.provider == "bank-statement")
        elif source == "commerce":
            stmt = stmt.where(AnalyticsEvent.provider != "bank-statement")
        elif source:
            stmt = stmt.where(AnalyticsEvent.provider == source)
        rows = list(db.scalars(stmt.order_by(AnalyticsEvent.occurred_at.desc(), AnalyticsEvent.id.desc())).all())
        mapped: list[TransactionRead] = []
        for event in rows:
            properties = json.loads(event.properties_json)
            event_status = {
                "purchase": "succeeded", "payment_succeeded": "succeeded", "refund": "refunded",
                "payment_failed": "failed", "payment_attempted": "pending",
            }.get(event.event_name, event.event_name.replace("_", " "))
            row = TransactionRead(
                id=event.id, order_id=event.order_id, source=event.provider,
                customer_id=properties.get("customer_id"), payment_method=properties.get("payment_method"),
                amount=event.revenue, currency=event.currency, status=event_status, occurred_at=event.occurred_at,
            )
            haystack = " ".join(filter(None, [row.order_id, row.source, row.customer_id, str(row.amount)])).lower()
            if query and query.lower().strip() not in haystack:
                continue
            if status and row.status != status:
                continue
            if currency and row.currency.upper() != currency.upper():
                continue
            mapped.append(row)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        start = (page - 1) * page_size
        return TransactionPage(items=mapped[start:start + page_size], total=len(mapped), page=page, page_size=page_size)

    def order_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, source: str | None = None) -> dict[str, int | float]:
        events = self._events_for_range(db, organization, start_date, end_date, source=source)
        created = [event for event in events if event.event_name in {"order_created", "purchase"}]
        return {
            "orders": len({event.order_id or event.id for event in created}),
            "revenue": round(sum(event.revenue for event in created), 2),
        }
