from uuid import uuid4
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Organization, Payment, ReversalLink, Storefront
from app.integrations.storefronts.base import CanonicalCommerceEvent
from app.main import app
from app.services.auth_service import AuthService
from app.services.payment_service import PaymentService

client = TestClient(app)


def _setup_tenant():
    suffix = uuid4().hex[:12]
    res = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"Risk {suffix}", "organization_slug": f"risk-{suffix}"},
    )
    assert res.status_code == 201
    api_key = res.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        org = AuthService().organization_for_key(db, api_key)
        storefront = Storefront(
            organization_id=org.id,
            name="Bank Statement Source",
            provider="sbi-statements",
            store_url="https://sbi.example.com",
        )
        db.add(storefront)
        db.commit()
        db.refresh(storefront)
        return org.id, storefront.id
    finally:
        db.close()


def test_reversal_matching_by_rrn():
    org_id, storefront_id = _setup_tenant()
    service = PaymentService()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)
        storefront = db.get(Storefront, storefront_id)

        # 1. First transaction: Debit of 100 USD at Swiggy with RRN
        debit_event = CanonicalCommerceEvent(
            event_name="purchase",
            order_id="debit-rrn-001",
            revenue=100.0,
            currency="USD",
            properties={
                "idempotency_key": "key-debit-001",
                "narration": "UPI/50291823/SWIGGY/ICICI RRN 998877112233",
            },
        )
        service.land_event(db, org, storefront, debit_event)
        db.commit()

        debit_payment = db.query(Payment).filter_by(
            organization_id=org.id,
            payment_ref="debit-rrn-001",
        ).first()
        assert debit_payment is not None
        assert debit_payment.status == "succeeded"
        assert debit_payment.channel == "UPI"
        assert debit_payment.entity_name == "Swiggy"
        assert debit_payment.reference_no == "998877112233"

        # 2. Second transaction: Return / Reversal with same RRN
        return_event = CanonicalCommerceEvent(
            event_name="purchase",
            order_id="return-rrn-002",
            revenue=100.0,
            currency="USD",
            properties={
                "idempotency_key": "key-return-002",
                "narration": "REV-UPI SWIGGY FAILED TXN REFUND RRN 998877112233",
            },
        )
        service.land_event(db, org, storefront, return_event)
        db.commit()

        db.refresh(debit_payment)
        return_payment = db.query(Payment).filter_by(
            organization_id=org.id,
            payment_ref="return-rrn-002",
        ).first()

        # Core user requirement verified:
        # 1. Previous transaction marked as failed
        assert debit_payment.status == "failed"
        assert debit_payment.failure_code == "RETURN_REVERSED"
        # 2. Second transaction marked as returned
        assert return_payment.status == "returned"
        assert return_payment.reversal_linked_id == debit_payment.id
        assert debit_payment.reversal_linked_id == return_payment.id

        # 3. Explicit ReversalLink audit entry exists
        link = db.query(ReversalLink).filter_by(
            organization_id=org.id,
            reversal_payment_id=return_payment.id,
        ).first()
        assert link is not None
        assert link.original_payment_id == debit_payment.id
        assert link.match_type == "RRN_EXACT"
        assert link.amount == 100.0
    finally:
        db.close()


def test_reversal_matching_by_entity_and_amount():
    org_id, storefront_id = _setup_tenant()
    service = PaymentService()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)
        storefront = db.get(Storefront, storefront_id)

        # Debit at ATM without explicit RRN
        debit_event = CanonicalCommerceEvent(
            event_name="purchase",
            order_id="atm-debit-001",
            revenue=200.0,
            currency="USD",
            properties={
                "idempotency_key": "key-atm-001",
                "narration": "ATM WDL CASH SBI KOTHUD PUNE",
            },
        )
        service.land_event(db, org, storefront, debit_event)
        db.commit()

        debit_payment = db.query(Payment).filter_by(
            organization_id=org.id,
            payment_ref="atm-debit-001",
        ).first()
        assert debit_payment.status == "succeeded"
        assert debit_payment.channel == "ATM"

        # Reversal / Return matching same ATM entity and amount
        return_event = CanonicalCommerceEvent(
            event_name="purchase",
            order_id="atm-return-002",
            revenue=200.0,
            currency="USD",
            properties={
                "idempotency_key": "key-atm-002",
                "narration": "REVERSAL ATM WDL CASH SBI KOTHUD PUNE DISPENSE FAILED",
            },
        )
        service.land_event(db, org, storefront, return_event)
        db.commit()

        db.refresh(debit_payment)
        return_payment = db.query(Payment).filter_by(
            organization_id=org.id,
            payment_ref="atm-return-002",
        ).first()

        assert debit_payment.status == "failed"
        assert return_payment.status == "returned"
        assert debit_payment.reversal_linked_id == return_payment.id
    finally:
        db.close()
