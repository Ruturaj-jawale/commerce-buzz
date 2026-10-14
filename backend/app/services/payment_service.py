"""Normalized universal payment and revenue-recovery model.

Canonical commerce events land here from the ingestion boundary (see
AnalyticsService.ingest). Landing is idempotent: every normalized row is keyed
by the event's idempotency key or a deterministic external reference, so
retries and duplicate deliveries converge instead of double-counting.
All queries are organization-scoped.
"""

import json
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Chargeback,
    CommerceOrder,
    Fee,
    OrderItem,
    Organization,
    Payment,
    PaymentAttempt,
    RecoveryAttempt,
    RecoveryCase,
    Refund,
    Storefront,
)
from app.integrations.storefronts.base import CanonicalCommerceEvent
from app.schemas.analytics import PaymentMetrics, RecoveryMetrics
from app.schemas.payments import (
    OrderMetricsRead,
    PaymentFailureRead,
    PaymentHistoryEntry,
    RevenueAtRisk,
    RevenueMetrics,
)

PAYMENT_LIFECYCLE_EVENTS = {
    "purchase",
    "order_created",
    "payment_attempted",
    "payment_failed",
    "payment_succeeded",
    "payment_captured",
    "payment_settled",
    "refund",
    "refund_created",
    "chargeback_created",
    "recovery_attempted",
    "recovery_succeeded",
}

_PAID_ORDER_STATUSES = ("paid", "partially_refunded", "refunded")


class PaymentService:
    def land_event(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent) -> None:
        if canonical.event_name not in PAYMENT_LIFECYCLE_EVENTS or not canonical.order_id:
            return
        key = canonical.properties.get("idempotency_key")
        if not key:
            return
        metadata = canonical.properties.get("metadata") or {}
        handler = self._handlers(canonical.event_name)
        handler(db, organization, storefront, canonical, str(key), metadata)

    # Landing

    def _handlers(self, event_name: str):
        return {
            "purchase": self._land_order,
            "order_created": self._land_order,
            "payment_attempted": self._land_payment_attempt,
            "payment_failed": self._land_payment_attempt,
            "payment_succeeded": self._land_payment_attempt,
            "payment_captured": self._land_payment_status,
            "payment_settled": self._land_payment_status,
            "refund": self._land_refund,
            "refund_created": self._land_refund,
            "chargeback_created": self._land_chargeback,
            "recovery_attempted": self._land_recovery,
            "recovery_succeeded": self._land_recovery,
        }[event_name]

    def _get_order(self, db: Session, organization: Organization, storefront: Storefront, order_ref: str) -> CommerceOrder | None:
        return db.scalar(
            select(CommerceOrder).where(
                CommerceOrder.organization_id == organization.id,
                CommerceOrder.storefront_id == storefront.id,
                CommerceOrder.order_ref == order_ref,
            )
        )

    def _ensure_order(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent) -> CommerceOrder:
        order = self._get_order(db, organization, storefront, canonical.order_id)  # type: ignore[arg-type]
        if order is None:
            order = CommerceOrder(
                organization_id=organization.id,
                storefront_id=storefront.id,
                order_ref=canonical.order_id,  # type: ignore[arg-type]
                customer_id=canonical.properties.get("customer_id"),
                status="created",
                amount=canonical.revenue,
                currency=canonical.currency,
                provider=storefront.provider,
                raw_json=json.dumps(canonical.properties),
            )
            db.add(order)
            db.flush()
        return order

    def _land_order(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        order = self._ensure_order(db, organization, storefront, canonical)
        if canonical.event_name != "purchase":
            return
        order.status = "paid"
        order.amount = canonical.revenue
        order.currency = canonical.currency
        if canonical.properties.get("customer_id"):
            order.customer_id = canonical.properties["customer_id"]
        order.items.clear()
        for item in canonical.properties.get("items") or []:
            quantity = int(item.get("quantity") or 1)
            order.items.append(
                OrderItem(
                    product_id=str(item.get("product_id") or "") or None,
                    product_name=str(item.get("name") or item.get("title") or "Unknown product"),
                    quantity=quantity,
                    unit_price=float(item.get("price") or 0),
                )
            )

    def _get_payment(self, db: Session, organization: Organization, storefront: Storefront, payment_ref: str) -> Payment | None:
        return db.scalar(
            select(Payment).where(
                Payment.organization_id == organization.id,
                Payment.external_ref == f"payment:{payment_ref}",
            )
        )

    def _ensure_payment(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, payment_ref: str) -> Payment:
        payment = self._get_payment(db, organization, storefront, payment_ref)
        if payment is None:
            order = self._ensure_order(db, organization, storefront, canonical)
            payment = Payment(
                organization_id=organization.id,
                storefront_id=storefront.id,
                order_id=order.id,
                payment_ref=payment_ref,
                status="attempted",
                amount=canonical.revenue,
                currency=canonical.currency,
                provider=storefront.provider,
                external_ref=f"payment:{payment_ref}",
                raw_json=json.dumps(canonical.properties),
            )
            db.add(payment)
            db.flush()
        return payment

    def _next_attempt_no(self, db: Session, payment_id: int) -> int:
        current = db.scalar(select(func.max(PaymentAttempt.attempt_no)).where(PaymentAttempt.payment_id == payment_id))
        return (current or 0) + 1

    def _land_payment_attempt(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        payment_ref = str(metadata.get("payment_id") or canonical.order_id)
        payment = self._ensure_payment(db, organization, storefront, canonical, payment_ref)
        failure_code = metadata.get("failure_code")
        failure_reason = metadata.get("failure_reason")
        if canonical.event_name == "payment_failed":
            payment.status = "failed"
            payment.failure_code = str(failure_code) if failure_code else None
            payment.failure_reason = str(failure_reason) if failure_reason else None
            self._open_recovery_case(db, organization, payment, canonical, failure_reason)
        elif canonical.event_name == "payment_succeeded":
            payment.status = "succeeded"
            payment.failure_code = None
            payment.failure_reason = None
            self._close_recovery_case(db, organization, payment, canonical.revenue)
        db.add(
            PaymentAttempt(
                organization_id=organization.id,
                payment_id=payment.id,
                attempt_no=int(metadata.get("attempt") or self._next_attempt_no(db, payment.id)),
                status={"payment_attempted": "attempted", "payment_failed": "failed", "payment_succeeded": "succeeded"}[canonical.event_name],
                amount=canonical.revenue,
                currency=canonical.currency,
                failure_code=str(failure_code) if failure_code else None,
                failure_reason=str(failure_reason) if failure_reason else None,
                external_ref=key,
            )
        )

    def _land_payment_status(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        payment_ref = str(metadata.get("payment_id") or canonical.order_id)
        payment = self._ensure_payment(db, organization, storefront, canonical, payment_ref)
        payment.status = canonical.event_name.replace("payment_", "")
        if canonical.event_name in {"payment_captured", "payment_settled"}:
            self._close_recovery_case(db, organization, payment, canonical.revenue)

    def _land_refund(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        order = self._ensure_order(db, organization, storefront, canonical)
        db.add(
            Refund(
                organization_id=organization.id,
                order_id=order.id,
                refund_ref=str(metadata.get("refund_id") or key),
                amount=canonical.revenue,
                currency=canonical.currency,
                reason=str(metadata.get("reason")) if metadata.get("reason") else None,
                external_ref=key,
                raw_json=json.dumps(canonical.properties),
            )
        )
        refunded = db.scalar(select(func.coalesce(func.sum(Refund.amount), 0.0)).where(Refund.order_id == order.id, Refund.organization_id == organization.id)) or 0.0
        refunded += canonical.revenue
        if order.status in {"paid", "partially_refunded", "refunded"}:
            order.status = "refunded" if refunded >= order.amount else "partially_refunded"

    def _land_chargeback(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        payment_ref = str(metadata.get("payment_id") or canonical.order_id)
        payment = self._ensure_payment(db, organization, storefront, canonical, payment_ref)
        payment.status = "chargeback"
        db.add(
            Chargeback(
                organization_id=organization.id,
                payment_id=payment.id,
                amount=canonical.revenue,
                currency=canonical.currency,
                status=str(metadata.get("status") or "open"),
                external_ref=key,
                raw_json=json.dumps(canonical.properties),
            )
        )

    def _open_case_for_order(self, db: Session, organization: Organization, order: CommerceOrder) -> RecoveryCase | None:
        return db.scalar(
            select(RecoveryCase)
            .where(RecoveryCase.organization_id == organization.id, RecoveryCase.order_id == order.id, RecoveryCase.status == "open")
            .order_by(RecoveryCase.id.desc())
        )

    def _open_recovery_case(self, db: Session, organization: Organization, payment: Payment, canonical: CanonicalCommerceEvent, failure_reason: Any) -> RecoveryCase:
        order = db.get(CommerceOrder, payment.order_id)
        case = self._open_case_for_order(db, organization, order)  # type: ignore[arg-type]
        if case is None:
            case = RecoveryCase(
                organization_id=organization.id,
                order_id=order.id,  # type: ignore[union-attr]
                payment_id=payment.id,
                customer_id=order.customer_id,  # type: ignore[union-attr]
                amount_at_risk=canonical.revenue,
                currency=canonical.currency,
                status="open",
                reason=str(failure_reason) if failure_reason else None,
                external_ref=f"case:{payment.payment_ref}",
                raw_json=json.dumps(canonical.properties),
            )
            db.add(case)
            db.flush()
        else:
            case.amount_at_risk = max(case.amount_at_risk, canonical.revenue)
            if failure_reason and not case.reason:
                case.reason = str(failure_reason)
        return case

    def _close_recovery_case(self, db: Session, organization: Organization, payment: Payment, recovered_amount: float) -> None:
        order = db.get(CommerceOrder, payment.order_id)
        if order is None:
            return
        case = self._open_case_for_order(db, organization, order)
        if case is not None:
            case.status = "recovered"
            case.recovered_amount = recovered_amount if recovered_amount > 0 else case.amount_at_risk
            case.closed_at = datetime.utcnow()

    def _land_recovery(self, db: Session, organization: Organization, storefront: Storefront, canonical: CanonicalCommerceEvent, key: str, metadata: dict[str, Any]) -> None:
        order = self._ensure_order(db, organization, storefront, canonical)
        case = self._open_case_for_order(db, organization, order)
        if case is None:
            case = RecoveryCase(
                organization_id=organization.id,
                order_id=order.id,
                payment_id=None,
                customer_id=order.customer_id,
                amount_at_risk=canonical.revenue,
                currency=canonical.currency,
                status="open",
                reason=str(metadata.get("reason")) if metadata.get("reason") else None,
                external_ref=f"case:order:{order.order_ref}",
                raw_json=json.dumps(canonical.properties),
            )
            db.add(case)
            db.flush()
        attempt_no = int(metadata.get("attempt") or ((db.scalar(select(func.max(RecoveryAttempt.attempt_no)).where(RecoveryAttempt.recovery_case_id == case.id)) or 0) + 1))
        db.add(
            RecoveryAttempt(
                organization_id=organization.id,
                recovery_case_id=case.id,
                attempt_no=attempt_no,
                status="attempted" if canonical.event_name == "recovery_attempted" else "succeeded",
                amount=canonical.revenue,
                currency=canonical.currency,
                external_ref=key,
            )
        )
        if canonical.event_name == "recovery_succeeded":
            case.status = "recovered"
            case.recovered_amount = canonical.revenue if canonical.revenue > 0 else case.amount_at_risk
            case.closed_at = datetime.utcnow()

    # Analytics

    def _range(self, statement, column, start_date: date | None, end_date: date | None):
        if start_date:
            statement = statement.where(column >= datetime.combine(start_date, time.min))
        if end_date:
            statement = statement.where(column <= datetime.combine(end_date, time.max))
        return statement

    def payment_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None) -> PaymentMetrics:
        statement = self._range(select(PaymentAttempt).where(PaymentAttempt.organization_id == organization.id), PaymentAttempt.occurred_at, start_date, end_date)
        attempts = list(db.scalars(statement).all())
        succeeded = [attempt for attempt in attempts if attempt.status == "succeeded"]
        failed = [attempt for attempt in attempts if attempt.status == "failed"]
        total = len(attempts)
        return PaymentMetrics(
            attempted=total,
            succeeded=len(succeeded),
            failed=len(failed),
            success_rate=round(len(succeeded) / total, 4) if total else 0.0,
            succeeded_amount=round(sum(attempt.amount for attempt in succeeded), 2),
            failed_amount=round(sum(attempt.amount for attempt in failed), 2),
        )

    def payment_failures(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None, limit: int = 50) -> list[PaymentFailureRead]:
        statement = (
            select(PaymentAttempt, Payment, CommerceOrder)
            .join(Payment, PaymentAttempt.payment_id == Payment.id)
            .join(CommerceOrder, Payment.order_id == CommerceOrder.id)
            .where(PaymentAttempt.organization_id == organization.id, PaymentAttempt.status == "failed")
            .order_by(PaymentAttempt.occurred_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        statement = self._range(statement, PaymentAttempt.occurred_at, start_date, end_date)
        rows = []
        for attempt, payment, order in db.execute(statement).all():
            case = db.scalar(
                select(RecoveryCase).where(RecoveryCase.organization_id == organization.id, RecoveryCase.order_id == order.id).order_by(RecoveryCase.id.desc())
            )
            rows.append(
                PaymentFailureRead(
                    attempt_id=attempt.id,
                    order_ref=order.order_ref,
                    payment_ref=payment.payment_ref,
                    customer_id=order.customer_id,
                    attempt_no=attempt.attempt_no,
                    amount=attempt.amount,
                    currency=attempt.currency,
                    failure_code=attempt.failure_code,
                    failure_reason=attempt.failure_reason,
                    recovery_status=case.status if case else None,
                    occurred_at=attempt.occurred_at,
                )
            )
        return rows

    def payment_recovery(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None) -> RecoveryMetrics:
        attempts_statement = self._range(select(RecoveryAttempt).where(RecoveryAttempt.organization_id == organization.id), RecoveryAttempt.occurred_at, start_date, end_date)
        attempts = list(db.scalars(attempts_statement).all())
        succeeded = [attempt for attempt in attempts if attempt.status == "succeeded"]
        recovered_cases = db.scalars(
            self._range(
                select(RecoveryCase).where(RecoveryCase.organization_id == organization.id, RecoveryCase.status == "recovered"),
                RecoveryCase.closed_at,
                start_date,
                end_date,
            )
        ).all()
        open_cases = db.scalars(
            select(RecoveryCase).where(RecoveryCase.organization_id == organization.id, RecoveryCase.status == "open")
        ).all()
        return RecoveryMetrics(
            attempted=len(attempts),
            succeeded=len(succeeded),
            recovered_amount=round(sum(case.recovered_amount for case in recovered_cases), 2),
            revenue_at_risk=round(sum(case.amount_at_risk for case in open_cases), 2),
        )

    def revenue_at_risk(self, db: Session, organization: Organization) -> RevenueAtRisk:
        cases = db.scalars(select(RecoveryCase).where(RecoveryCase.organization_id == organization.id)).all()
        by_status: dict[str, list[RecoveryCase]] = {}
        for case in cases:
            by_status.setdefault(case.status, []).append(case)
        open_cases = by_status.get("open", [])
        recovered_cases = by_status.get("recovered", [])
        lost_cases = by_status.get("lost", [])
        return RevenueAtRisk(
            open_amount=round(sum(case.amount_at_risk for case in open_cases), 2),
            open_cases=len(open_cases),
            recovered_amount=round(sum(case.recovered_amount for case in recovered_cases), 2),
            recovered_cases=len(recovered_cases),
            lost_amount=round(sum(case.amount_at_risk - case.recovered_amount for case in lost_cases), 2),
            lost_cases=len(lost_cases),
        )

    def _history_for_orders(self, db: Session, organization: Organization, orders: list[CommerceOrder]) -> list[PaymentHistoryEntry]:
        entries: list[PaymentHistoryEntry] = []
        for order in orders:
            entries.append(PaymentHistoryEntry(kind="order", status=order.status, order_ref=order.order_ref, amount=order.amount, currency=order.currency, occurred_at=order.occurred_at))
            payments = db.scalars(select(Payment).where(Payment.organization_id == organization.id, Payment.order_id == order.id)).all()
            for payment in payments:
                attempts = db.scalars(select(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)).all()
                for attempt in attempts:
                    entries.append(PaymentHistoryEntry(kind="payment_attempt", status=attempt.status, order_ref=order.order_ref, amount=attempt.amount, currency=attempt.currency, occurred_at=attempt.occurred_at))
                chargebacks = db.scalars(select(Chargeback).where(Chargeback.payment_id == payment.id)).all()
                for chargeback in chargebacks:
                    entries.append(PaymentHistoryEntry(kind="chargeback", status=chargeback.status, order_ref=order.order_ref, amount=chargeback.amount, currency=chargeback.currency, occurred_at=chargeback.occurred_at))
            refunds = db.scalars(select(Refund).where(Refund.organization_id == organization.id, Refund.order_id == order.id)).all()
            for refund in refunds:
                entries.append(PaymentHistoryEntry(kind="refund", status="completed", order_ref=order.order_ref, amount=refund.amount, currency=refund.currency, occurred_at=refund.occurred_at))
            cases = db.scalars(select(RecoveryCase).where(RecoveryCase.organization_id == organization.id, RecoveryCase.order_id == order.id)).all()
            for case in cases:
                attempts = db.scalars(select(RecoveryAttempt).where(RecoveryAttempt.recovery_case_id == case.id)).all()
                for attempt in attempts:
                    entries.append(PaymentHistoryEntry(kind="recovery_attempt", status=attempt.status, order_ref=order.order_ref, amount=attempt.amount, currency=attempt.currency, occurred_at=attempt.occurred_at))
        return sorted(entries, key=lambda entry: (entry.occurred_at, entry.order_ref, entry.kind))

    def customer_payment_history(self, db: Session, organization: Organization, customer_id: str) -> list[PaymentHistoryEntry]:
        orders = db.scalars(
            select(CommerceOrder)
            .where(CommerceOrder.organization_id == organization.id, CommerceOrder.customer_id == customer_id)
            .order_by(CommerceOrder.occurred_at)
        ).all()
        return self._history_for_orders(db, organization, list(orders))

    def transaction_lifecycle(self, db: Session, organization: Organization, order_ref: str) -> list[PaymentHistoryEntry]:
        orders = db.scalars(
            select(CommerceOrder).where(CommerceOrder.organization_id == organization.id, CommerceOrder.order_ref == order_ref).order_by(CommerceOrder.id)
        ).all()
        return self._history_for_orders(db, organization, list(orders))

    def revenue_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None) -> RevenueMetrics:
        order_statement = self._range(
            select(CommerceOrder).where(
                CommerceOrder.organization_id == organization.id,
                CommerceOrder.status.in_(_PAID_ORDER_STATUSES),
            ),
            CommerceOrder.occurred_at,
            start_date,
            end_date,
        )
        gross = sum(order.amount for order in db.scalars(order_statement).all())
        refunds = db.scalars(self._range(select(Refund).where(Refund.organization_id == organization.id), Refund.occurred_at, start_date, end_date)).all()
        chargebacks = db.scalars(self._range(select(Chargeback).where(Chargeback.organization_id == organization.id), Chargeback.occurred_at, start_date, end_date)).all()
        fees = db.scalars(self._range(select(Fee).where(Fee.organization_id == organization.id), Fee.occurred_at, start_date, end_date)).all()
        refunds_total = round(sum(refund.amount for refund in refunds), 2)
        chargebacks_total = round(sum(chargeback.amount for chargeback in chargebacks), 2)
        fees_total = round(sum(fee.amount for fee in fees), 2)
        gross = round(gross, 2)
        return RevenueMetrics(gross=gross, refunds=refunds_total, chargebacks=chargebacks_total, fees=fees_total, net=round(gross - refunds_total - chargebacks_total - fees_total, 2))

    def order_metrics(self, db: Session, organization: Organization, start_date: date | None = None, end_date: date | None = None) -> OrderMetricsRead:
        statement = self._range(
            select(CommerceOrder).where(
                CommerceOrder.organization_id == organization.id,
                CommerceOrder.status.in_(_PAID_ORDER_STATUSES),
            ),
            CommerceOrder.occurred_at,
            start_date,
            end_date,
        )
        orders = db.scalars(statement).all()
        revenue = round(sum(order.amount for order in orders), 2)
        count = len(orders)
        return OrderMetricsRead(orders=count, revenue=revenue, average_order_value=round(revenue / count, 2) if count else 0.0)
