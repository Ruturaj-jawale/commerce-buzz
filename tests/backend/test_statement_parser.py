"""Unit tests for statement narration parsing and channel/entity classification."""

import pytest
from app.services.statement_parser import parse_statement_narration


def test_parse_atm_withdrawal():
    parsed = parse_statement_narration("ATM WDL CASH SBI KOTHUD PUNE TXN 982341209812")
    assert parsed.channel == "ATM"
    assert "ATM" in parsed.entity_name
    assert "Kothud" in parsed.entity_name or "Pune" in parsed.entity_name
    assert parsed.reference_no == "982341209812"
    assert parsed.is_reversal is False


def test_parse_upi_merchant():
    parsed = parse_statement_narration("UPI/50291823/SWIGGY/ICICI/order492")
    assert parsed.channel == "UPI"
    assert parsed.entity_name == "Swiggy"
    assert parsed.is_reversal is False


def test_parse_card_swipe_pos():
    parsed = parse_statement_narration("POS 401234xxxx STARBUCKS PUNE IN REF 1092837465")
    assert parsed.channel == "CARD_SWIPE"
    assert parsed.entity_name == "Starbucks"
    assert parsed.reference_no == "1092837465"
    assert parsed.is_reversal is False


def test_parse_online_ecommerce():
    parsed = parse_statement_narration("ECOM 3DS AMAZON PAY INDIA RRN 409182736451")
    assert parsed.channel == "ONLINE_CARD"
    assert parsed.entity_name == "Amazon"
    assert parsed.reference_no == "409182736451"
    assert parsed.is_reversal is False


def test_parse_reversal_refund():
    parsed = parse_statement_narration("REV-UPI/50291823/SWIGGY/FAILED TXN REFUND")
    assert parsed.channel == "UPI"
    assert parsed.entity_name == "Swiggy"
    assert parsed.is_reversal is True
    assert parsed.direction_hint == "CREDIT"


def test_parse_bank_fee():
    parsed = parse_statement_narration("ANNUAL CARD FEE CHG + 18% GST")
    assert parsed.channel == "FEE"
    assert "Fee" in parsed.entity_name or "Charges" in parsed.entity_name


def test_sanitize_sensitive_data_pii_pci():
    raw_statement = (
        "UPI/50291823/SWIGGY/ICICI A/C 9876543210123 PAN: ABCDE1234F "
        "CARD 4532 0150 1234 5678 CVV 452 Mob: +91 9876543210 Email: user@example.com RRN 50291823"
    )
    parsed = parse_statement_narration(raw_statement)

    assert parsed.channel == "UPI"
    assert parsed.entity_name == "Swiggy"
    assert parsed.reference_no == "50291823"

    # Verify PII/PCI redaction
    assert "9876543210123" not in parsed.raw_narration
    assert "[REDACTED_ACCT]" in parsed.raw_narration

    assert "ABCDE1234F" not in parsed.raw_narration
    assert "[REDACTED_PAN]" in parsed.raw_narration

    assert "4532 0150 1234 5678" not in parsed.raw_narration
    assert "[REDACTED_CARD_PAN]" in parsed.raw_narration

    assert "452" not in parsed.raw_narration
    assert "[REDACTED_CVV]" in parsed.raw_narration

    assert "9876543210" not in parsed.raw_narration
    assert "[REDACTED_PHONE]" in parsed.raw_narration

    assert "user@example.com" not in parsed.raw_narration
    assert "[REDACTED_EMAIL]" in parsed.raw_narration

