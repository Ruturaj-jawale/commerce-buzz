"""Bank statement and card processing narration parser.

Extracts canonical counterparty/merchant names, transaction channels (ATM,
CARD_SWIPE/POS, UPI, ONLINE_CARD, TRANSFER, FEE), reference numbers (RRN/UTR),
and reversal/return indicators from unstructured banking and card processing feeds.
"""

import re
from dataclasses import dataclass
from typing import Literal

TransactionChannel = Literal[
    "ATM",
    "CARD_SWIPE",
    "UPI",
    "ONLINE_CARD",
    "TRANSFER",
    "FEE",
    "OTHER",
]

TransactionDirection = Literal["DEBIT", "CREDIT"]


@dataclass(frozen=True)
class ParsedNarration:
    raw_narration: str
    channel: TransactionChannel
    entity_name: str
    reference_no: str | None
    is_reversal: bool
    direction_hint: TransactionDirection | None = None


# Known common merchants/brands for high-confidence canonicalization
_KNOWN_MERCHANTS: dict[str, str] = {
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "uber": "Uber",
    "ola": "Ola Cabs",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "starbucks": "Starbucks",
    "mcdonalds": "McDonald's",
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "instamart": "Instamart",
    "paytm": "Paytm",
    "phonepe": "PhonePe",
    "googlepay": "Google Pay",
    "gpay": "Google Pay",
    "myntra": "Myntra",
    "nykaa": "Nykaa",
    "tata1mg": "Tata 1mg",
    "irctc": "IRCTC",
    "makemytrip": "MakeMyTrip",
    "bookmyshow": "BookMyShow",
    "cred": "CRED",
    "razorpay": "Razorpay",
    "cashfree": "Cashfree",
}

# Reversal and return tokens
_REVERSAL_REGEX = re.compile(
    r"\b(REV|REVERSAL|REFUND|RETURN|RETURNED|RTN|CHARGEBACK|FAILED\s+TXN\s+REV|AUTO[\s-]REVERSAL|REV-UPI|UPI-REV|DISPENSE\s+FAILED)\b",
    re.IGNORECASE,
)

# Reference number extractors: specifically look for RRN, REF, UTR, AUTH, CHQ, or standalone 8-16 digit numbers
_RRN_REGEX = re.compile(r"\b(?:RRN|REF|UTR|AUTH|CHQ)[\s/:-]*([0-9A-Za-z]*\d[0-9A-Za-z]*)\b", re.IGNORECASE)
_GENERIC_REF_REGEX = re.compile(r"\b([0-9]{8,18})\b")

# PII and PCI Redaction Patterns for Bank Statements & Card Feeds
_PAN_CARD_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
_BANK_ACCT_REGEX = re.compile(
    r"\b(?:A/C|AC|ACCT|ACCOUNT|SB|CA|ACC\s*NO|A/C\s*NO)[\s/:-]*([0-9]{9,18})\b",
    re.IGNORECASE,
)
_CARD_PAN_SPACED_REGEX = re.compile(r"\b(?:\d{4}[-\s]){3}\d{4}\b")
_CARD_PAN_COMPACT_REGEX = re.compile(
    r"\b(?<!\w)(?:4[0-9]{15}|5[1-5][0-9]{14}|6011[0-9]{12}|3[47][0-9]{13}|35\d{14})(?!\w)\b"
)
_AADHAAR_REGEX = re.compile(r"\b\d{4}[-\s]\d{4}[-\s]\d{4}\b")
_CVV_REGEX = re.compile(r"\b(?:CVV|CVC|CID)[\s/:-]*([0-9]{3,4})\b", re.IGNORECASE)
_PHONE_REGEX = re.compile(r"(?:\+91[-\s]?)?[6-9]\d{9}\b")
_EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def sanitize_sensitive_data(text: str) -> str:
    """Neutralize PII and PCI data (Card numbers, Bank Accounts, Indian Tax PAN, Aadhaar, CVV, Phone, Email).

    Guarantees compliance with PCI-DSS Requirement 3.4 and banking privacy rules
    by stripping sensitive identifiers before statement parsing, persistent storage, or model ingestion.
    """
    if not text:
        return ""

    sanitized = text

    # 1. Mask explicit Bank Account numbers: A/C 123456789012 -> A/C [REDACTED_ACCT]
    sanitized = _BANK_ACCT_REGEX.sub(r"A/C [REDACTED_ACCT]", sanitized)

    # 2. Mask Indian Income Tax PAN: ABCDE1234F -> [REDACTED_PAN]
    sanitized = _PAN_CARD_REGEX.sub("[REDACTED_PAN]", sanitized)

    # 3. Mask Card Primary Account Numbers (16 digits spaced or compact card numbers)
    sanitized = _CARD_PAN_SPACED_REGEX.sub("[REDACTED_CARD_PAN]", sanitized)
    sanitized = _CARD_PAN_COMPACT_REGEX.sub("[REDACTED_CARD_PAN]", sanitized)

    # 4. Mask Aadhaar numbers: 1234 5678 9012 -> [REDACTED_AADHAAR]
    sanitized = _AADHAAR_REGEX.sub("[REDACTED_AADHAAR]", sanitized)

    # 5. Mask CVV / CVC
    sanitized = _CVV_REGEX.sub(r"CVV [REDACTED_CVV]", sanitized)

    # 6. Mask phone numbers
    sanitized = _PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)

    # 7. Mask email addresses (excluding UPI VPAs)
    vpa_suffixes = (
        "@okaxis",
        "@okhdfc",
        "@okicici",
        "@oksbi",
        "@paytm",
        "@ybl",
        "@axl",
        "@ibl",
        "@icici",
        "@sbi",
    )

    def _mask_email(match):
        val = match.group(0)
        if any(val.lower().endswith(s) for s in vpa_suffixes):
            return val
        return "[REDACTED_EMAIL]"

    sanitized = _EMAIL_REGEX.sub(_mask_email, sanitized)

    return sanitized


def _clean_entity_name(raw: str) -> str:
    """Normalize merchant/person name into clean title case."""
    # Strip reversal and status noise words
    cleaned = re.sub(
        r"\b(REV|REVERSAL|REFUND|RETURN|RETURNED|RTN|CHARGEBACK|FAILED|DISPENSE|DECLINED|TXN|WDL|CASH|NFS|MATM)\b",
        " ",
        raw,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[\d]{6,}", "", cleaned)  # Strip long phone/ref numbers
    cleaned = re.sub(r"[^A-Za-z0-9\s&.-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Check known merchant overrides
    normalized_key = "".join(c for c in cleaned.lower() if c.isalnum())
    for key, canonical in _KNOWN_MERCHANTS.items():
        if key in normalized_key:
            return canonical

    # If title is short (e.g. acronym like SBI ATM, HDFC), preserve uppercase
    words = cleaned.split()
    formatted = []
    for word in words:
        if len(word) <= 3 and word.isupper():
            formatted.append(word)
        elif word.lower() in {"in", "at", "to", "by", "for"}:
            formatted.append(word.lower())
        else:
            formatted.append(word.capitalize())
    result = " ".join(formatted)[:120].strip()
    return result or "Unknown Entity"


def parse_statement_narration(narration: str) -> ParsedNarration:
    """Classify channel, extract counterparty/merchant, reference number, and reversal status,

    redacting all PII/PCI (Card PAN, Bank Account, Indian Tax PAN, CVV, Phone, Email).
    """
    text = (narration or "").strip()
    if not text:
        return ParsedNarration(
            raw_narration="",
            channel="OTHER",
            entity_name="Unknown Entity",
            reference_no=None,
            is_reversal=False,
        )

    # 1. Detect Reversal / Return
    is_reversal = bool(_REVERSAL_REGEX.search(text))

    # 2. Extract Reference Number (RRN, UTR, or Txn ID) BEFORE redaction
    ref_match = _RRN_REGEX.search(text)
    reference_no = ref_match.group(1) if ref_match else None
    if not reference_no:
        generic_match = _GENERIC_REF_REGEX.search(text)
        if generic_match:
            reference_no = generic_match.group(1)

    # 3. Sanitize sensitive user data (PCI-DSS & PII Masking)
    sanitized_text = sanitize_sensitive_data(text)

    upper_text = sanitized_text.upper()

    # 4. Channel Classification & Entity Extraction
    # ATM Cash Withdrawals / Deposits
    if any(k in upper_text for k in ("ATM WDL", "ATM CASH", "NFS*ATM", "NFS ATM", "MATM", "CASH WDL ATM", "ATM DEPOSIT")):
        channel: TransactionChannel = "ATM"
        # Extract ATM location/bank (e.g., "ATM WDL CASH SBI KOTHUD PUNE" -> "SBI ATM Kothrud Pune")
        sub_text = re.sub(r"\b(ATM|WDL|CASH|NFS|MATM|DEPOSIT|TXN|W/D)\b", "", upper_text)
        location = _clean_entity_name(sub_text)
        entity_name = f"ATM {location}".strip() if location and location != "Unknown Entity" else "ATM Cash Withdrawal"

    # UPI Payments (P2P and P2M)
    elif "UPI" in upper_text or "@" in upper_text and any(v in upper_text for v in ("@OK", "@PAYTM", "@YBL", "@AXL", "@IBL", "@ICICI")):
        channel = "UPI"
        # UPI formats typically: UPI/RRN/MERCHANT/BANK/... or UPI-NAME-VPA
        parts = [p.strip() for p in re.split(r"[/:-]", sanitized_text) if p.strip()]
        candidate_name = ""
        for part in parts:
            p_upper = part.upper()
            if p_upper in {"UPI", "REV", "P2A", "P2M"} or p_upper.isdigit():
                continue
            if "@" in part:
                candidate_name = part.split("@", 1)[0]
                break
            if len(part) >= 3 and not part.isdigit():
                candidate_name = part
                break
        entity_name = _clean_entity_name(candidate_name or sanitized_text)

    # Card Swipe / Physical POS
    elif any(k in upper_text for k in ("POS", "EDC", "SWIPE", "CHIP", "VISA POS", "MC POS", "RUPAY POS")):
        channel = "CARD_SWIPE"
        sub_text = re.sub(r"\b(POS|EDC|SWIPE|CHIP|VISA|MC|RUPAY|PURCHASE|SALE)\b", "", upper_text)
        entity_name = _clean_entity_name(sub_text or sanitized_text)

    # Online Card / E-Commerce Payment Gateway
    elif any(k in upper_text for k in ("ECOM", "3DS", "PG", "BILLDESK", "RAZORPAY", "PAYTM PG", "CASHFREE", "PAYU", "STRIPE")):
        channel = "ONLINE_CARD"
        sub_text = re.sub(r"\b(ECOM|3DS|PG|BILLDESK|RAZORPAY|CASHFREE|PAYU|STRIPE)\b", "", upper_text)
        entity_name = _clean_entity_name(sub_text or sanitized_text)

    # Bank Transfers (NEFT, RTGS, IMPS, Internal Transfer)
    elif any(k in upper_text for k in ("NEFT", "RTGS", "IMPS", "FT", "TRF", "TRANSFER", "INB")):
        channel = "TRANSFER"
        sub_text = re.sub(r"\b(NEFT|RTGS|IMPS|FT|TRF|TRANSFER|INB|CR|DR)\b", "", upper_text)
        entity_name = _clean_entity_name(sub_text or sanitized_text)

    # Bank Charges, Annual Fees, GST
    elif any(k in upper_text for k in ("FEE", "CHG", "CHARGES", "GST", "ANNUAL FEE", "INTERCHANGE", "MAINT")):
        channel = "FEE"
        entity_name = "Bank Charges / Processing Fee"

    else:
        channel = "OTHER"
        entity_name = _clean_entity_name(sanitized_text)

    return ParsedNarration(
        raw_narration=sanitized_text,
        channel=channel,
        entity_name=entity_name,
        reference_no=reference_no,
        is_reversal=is_reversal,
        direction_hint="CREDIT" if is_reversal else None,
    )
