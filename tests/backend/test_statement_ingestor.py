"""Unit and integration test suite for multi-format bank statement ingestion pipeline.

Tests CSV/Excel ingestion, PII/PCI sanitization, automated reversal reconciliation,
multi-tenant isolation, REST endpoint upload, and MCP tool execution.
"""

import io
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.db.database import SessionLocal
from app.db.models import Organization, Payment, ReversalLink
from app.main import app
from app.mcp.server import create_mcp_server
from app.services.auth_service import AuthService
from app.services.statement_ingestor import ingest_and_record_statement, ingest_bank_statement

client = TestClient(app)


def _create_tenant() -> tuple[dict[str, str], int]:
    suffix = uuid4().hex[:12]
    res = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"BankTest {suffix}", "organization_slug": f"banktest-{suffix}"},
    )
    assert res.status_code == 201
    api_key = res.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        org = AuthService().organization_for_key(db, api_key)
        return {"X-API-Key": api_key}, org.id
    finally:
        db.close()


def test_ingest_csv_statement_with_reversal_linking():
    headers, org_id = _create_tenant()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)

        csv_content = (
            "Date,Narration,Debit,Credit,Balance\n"
            "2026-10-01,ATM WDL CASH SBI KOTHRUD PUNE RRN 112233445566,2000.00,,48000.00\n"
            "2026-10-02,UPI/998877/SWIGGY/HDFC RRN 223344556677,450.00,,47550.00\n"
            "2026-10-03,REV ATM CASH DISPENSE FAIL RRN 112233445566,,2000.00,49550.00\n"
        ).encode("utf-8")

        report = ingest_and_record_statement(
            db=db,
            organization=org,
            content=csv_content,
            filename="sbi_october_statement.csv",
        )

        assert report.rows_parsed == 3
        assert report.rows_ingested == 3
        assert report.reversals_linked == 1
        assert report.total_debit_amount == 2450.0
        assert report.total_credit_amount == 2000.0
        assert report.format_detected == "CSV"

        # Check DB states
        payments = db.query(Payment).filter_by(organization_id=org.id).all()
        assert len(payments) == 3

        atm_debit = next(p for p in payments if p.reference_no == "112233445566" and p.direction == "DEBIT")
        atm_reversal = next(p for p in payments if p.reference_no == "112233445566" and p.direction == "CREDIT")

        # Original debit must be failed
        assert atm_debit.status == "failed"
        assert atm_debit.failure_code == "RETURN_REVERSED"
        assert atm_debit.channel == "ATM"
        assert "SBI" in atm_debit.entity_name

        # Reversal credit must be returned
        assert atm_reversal.status == "returned"
        assert atm_reversal.reversal_linked_id == atm_debit.id
        assert atm_debit.reversal_linked_id == atm_reversal.id

        # Reversal link audit row
        rev_link = db.query(ReversalLink).filter_by(organization_id=org.id).first()
        assert rev_link is not None
        assert rev_link.original_payment_id == atm_debit.id
        assert rev_link.reversal_payment_id == atm_reversal.id
        assert rev_link.match_type == "RRN_EXACT"
    finally:
        db.close()


def test_ingest_excel_statement_with_pii_sanitization():
    headers, org_id = _create_tenant()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)

        wb = Workbook()
        ws = wb.active
        ws.title = "Statement"
        ws.append(["Txn Date", "Particulars", "Debit Amt", "Credit Amt", "Closing Balance"])
        # Includes raw PAN 4111111111114321 and account number
        ws.append(["2026-10-05", "POS SWIPE CARD 4111111111114321 A/C 987654321012 STARBUCKS", 850.0, "", 46700.0])

        buf = io.BytesIO()
        wb.save(buf)
        excel_content = buf.getvalue()

        report = ingest_and_record_statement(
            db=db,
            organization=org,
            content=excel_content,
            filename="hdfc_card_feed.xlsx",
        )

        assert report.rows_parsed == 1
        assert report.rows_ingested == 1
        assert report.format_detected == "Excel"

        payment = db.query(Payment).filter_by(organization_id=org.id).first()
        assert payment is not None
        assert payment.channel == "CARD_SWIPE"
        assert "Starbucks" in payment.entity_name
        # PII Card PAN must NOT exist in raw form
        assert "4111111111114321" not in payment.raw_narration
        assert "[REDACTED_CARD_PAN]" in payment.raw_narration
        assert "987654321012" not in payment.raw_narration
        assert "[REDACTED_ACCT]" in payment.raw_narration
    finally:
        db.close()


def test_multi_tenant_isolation_in_statement_ingestion():
    headers_a, org_a_id = _create_tenant()
    headers_b, org_b_id = _create_tenant()

    db = SessionLocal()
    try:
        org_a = db.get(Organization, org_a_id)
        org_b = db.get(Organization, org_b_id)

        csv_content = (
            "Date,Narration,Debit,Credit,Balance\n"
            "2026-10-01,ATM WDL CASH SBI PUNE RRN 778899001122,5000.00,,20000.00\n"
        ).encode("utf-8")

        ingest_and_record_statement(
            db=db,
            organization=org_a,
            content=csv_content,
            filename="tenant_a_stmt.csv",
        )

        # Org A has 1 payment
        payments_a = db.query(Payment).filter_by(organization_id=org_a.id).all()
        assert len(payments_a) == 1

        # Org B has 0 payments
        payments_b = db.query(Payment).filter_by(organization_id=org_b.id).all()
        assert len(payments_b) == 0

        # Verify through REST risk assessment API
        res_a = client.get("/api/analytics/risk-assessment", headers=headers_a)
        assert res_a.status_code == 200
        assert res_a.json()["total_transactions"] == 1

        res_b = client.get("/api/analytics/risk-assessment", headers=headers_b)
        assert res_b.status_code == 200
        assert res_b.json()["total_transactions"] == 0
    finally:
        db.close()


def test_upload_statement_api_endpoint():
    headers, org_id = _create_tenant()

    csv_content = (
        "Date,Narration,Debit,Credit,Balance\n"
        "2026-10-10,UPI/12345/AMAZON INDIA RRN 999888777666,1299.00,,18701.00\n"
    ).encode("utf-8")

    res = client.post(
        "/api/analytics/statements/upload",
        files={"file": ("axis_upi_stmt.csv", io.BytesIO(csv_content), "text/csv")},
        headers=headers,
    )

    assert res.status_code == 200
    data = res.json()
    assert data["rows_parsed"] == 1
    assert data["rows_ingested"] == 1
    assert data["format_detected"] == "CSV"
    assert data["total_debit_amount"] == 1299.0


def test_ingest_statement_file_mcp_tool():
    headers, org_id = _create_tenant()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)
        server = create_mcp_server(org)

        csv_content = (
            "Date,Narration,Debit,Credit,Balance\n"
            "2026-10-12,MATM CASH WDL RRN 443322110099,1000.00,,9000.00\n"
        )
        with NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            result = server.call_tool("ingest_statement_file", {"file_path": temp_path})
            assert result["rows_parsed"] == 1
            assert result["rows_ingested"] == 1
            assert result["format_detected"] == "CSV"
            assert result["total_debit_amount"] == 1000.0
        finally:
            Path(temp_path).unlink(missing_ok=True)
    finally:
        db.close()


def test_ingest_statement_with_bank_preset_and_custom_headers():
    headers, org_id = _create_tenant()
    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)

        # IPPB format: DATE, TRAN ID, TRANSACTION PARTICULARS, WITHDRWAL, DEPOSIT, BALANCE
        ippb_csv = (
            "DATE,TRAN ID,TRANSACTION PARTICULARS,WITHDRWAL,DEPOSIT,BALANCE\n"
            "17-08-2026,S79045856,UPI~622999096870~CR~Ruturaj,,650.00,873.00\n"
            "18-08-2026,S17829476,UPI~104884675612~DR~RUTURAJ,500.00,,373.00\n"
        ).encode("utf-8")

        rows, res = ingest_bank_statement(
            content=ippb_csv,
            filename="ippb_statement.csv",
            organization_id=org_id,
            bank_preset="ippb",
        )
        assert len(rows) == 2
        assert rows[0].amount == 650.0
        assert rows[0].direction == "CREDIT"
        assert rows[1].amount == 500.0
        assert rows[1].direction == "DEBIT"

        # Custom headers test
        custom_csv = (
            "TxDate,CustomNotes,PaidOut,ReceivedIn,RemainingBal\n"
            "2026-09-01,Supplier Payout,250.00,,9750.00\n"
            "2026-09-02,Client Deposit,,1200.00,10950.00\n"
        ).encode("utf-8")

        custom_mapping = {
            "date": "TxDate",
            "narration": "CustomNotes",
            "debit": "PaidOut",
            "credit": "ReceivedIn",
            "balance": "RemainingBal",
        }

        report = ingest_and_record_statement(
            db=db,
            organization=org,
            content=custom_csv,
            filename="custom_bank_export.csv",
            custom_headers=custom_mapping,
        )
        assert report.rows_parsed == 2
        assert report.rows_ingested == 2
        assert report.total_debit_amount == 250.0
        assert report.total_credit_amount == 1200.0
    finally:
        db.close()


def test_upload_statement_api_with_bank_preset_and_custom_headers():
    headers, org_id = _create_tenant()

    csv_data = (
        "Date,Transaction Reference,Debit,Credit,Balance,Ref.No./Chq.No.\n"
        "2026-08-10,UPI/Transfer/Dinner,350.00,,4650.00,UPI1234567890\n"
    ).encode("utf-8")

    import json
    res = client.post(
        "/api/risk/statements/upload",
        files={"file": ("sbi_stmt.csv", csv_data, "text/csv")},
        data={
            "bank_preset": "sbi",
            "custom_headers": json.dumps({"narration": "Transaction Reference"}),
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["rows_parsed"] == 1
    assert data["rows_ingested"] == 1
    assert data["total_debit_amount"] == 350.0

