"""Declarative mapping engine: extract canonical commerce events from arbitrary rows.

A mapping config connects canonical target fields to source locations. Source
locations may be flat column names ("Order #") or dotted paths ("total.amount")
for nested JSON payloads, so the same engine serves CSV/Excel rows, webhook
payloads, and provider presets:

{
  "event_name": {"const": "purchase"},
  "order_id": {"column": "Order #"},
  "revenue": {"column": "Total"},
  "currency": {"const": "USD"},
  "customer_id": {"column": "Email"},
  "occurred_at": {"column": "Date"},
  "items": {
    "product_id": {"column": "SKU"},
    "name": {"column": "Product"},
    "price": {"column": "Price"},
    "quantity": {"column": "Qty"}
  }
}

When an "items" mapping is present, rows are grouped by order_id and each row
contributes one line item (flat line-item exports such as GoDaddy/Shopify
order exports). Order-level fields are taken from the first row of each group.
Without an "items" mapping, each row becomes one event.
"""

from datetime import date, datetime
from typing import Any

from app.integrations.storefronts.base import CANONICAL_EVENTS

TARGET_FIELDS = ("event_name", "order_id", "revenue", "currency", "customer_id", "occurred_at")
ITEM_FIELDS = ("product_id", "name", "price", "quantity")

MAX_ISSUES_STORED = 200

# Normalized aliases (lowercase, alphanumeric only) used for auto-suggestion,
# ordered from most to least specific per target field.
FIELD_ALIASES: dict[str, list[str]] = {
    "order_id": ["orderid", "ordernumber", "orderno", "ordernum", "transactionid", "refno", "referenceno", "rrn", "utr", "chequeno", "chqrefno", "authcode", "order", "reference", "id"],
    "revenue": ["revenue", "grandtotal", "ordertotal", "totalamount", "total", "amount", "debit", "withdrawal", "debitamount", "dr", "txnamount", "saleamount", "sales", "ordervalue", "gross", "credit", "deposit"],
    "currency": ["currencycode", "currency", "ccy"],
    "customer_id": ["customerid", "customeremail", "customer", "email", "buyeremail", "buyer", "client", "customername", "account", "accountno", "accno", "cardno", "cardnumber"],
    "event_name": ["eventname", "event", "status", "type", "action", "drcr"],
    "occurred_at": ["createdat", "orderdate", "transactiondate", "txndate", "valuedate", "postingdate", "statementdate", "purchasedate", "purchasedat", "paidat", "placedat", "occurredat", "datetime", "timestamp", "created", "date"],
    "items.product_id": ["productsku", "itemsku", "variantsku", "sku", "productid", "itemid", "mcc", "terminalid"],
    "items.name": ["narration", "particulars", "description", "remarks", "transactiondetails", "merchant", "merchantname", "productname", "producttitle", "itemname", "itemtitle", "product", "item", "title"],
    "items.price": ["unitprice", "itemprice", "priceeach", "rate", "price"],
    "items.quantity": ["itemquantity", "linequantity", "quantity", "qty", "units", "count"],
}

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
)


def _normalize(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def suggest_mapping(columns: list[str]) -> dict[str, Any]:
    by_normalized = {_normalize(column): column for column in columns}
    suggested: dict[str, Any] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in by_normalized:
                entry: dict[str, Any] = {"column": by_normalized[alias]}
                if field.startswith("items."):
                    suggested.setdefault("items", {})[field.split(".", 1)[1]] = entry
                else:
                    suggested[field] = entry
                break
    return suggested


def validate_mapping(mapping: Any, columns: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(mapping, dict):
        return ["mapping must be an object"]
    available = set(columns)
    for target, entry in mapping.items():
        if target == "items":
            if not isinstance(entry, dict):
                errors.append("items mapping must be an object")
                continue
            for item_field, item_entry in entry.items():
                if item_field not in ITEM_FIELDS:
                    errors.append(f"unknown items target '{item_field}'")
                    continue
                errors.extend(_validate_entry(f"items.{item_field}", item_entry, available))
        elif target in TARGET_FIELDS:
            errors.extend(_validate_entry(target, entry, available))
            if target == "event_name" and isinstance(entry, dict) and "const" in entry and entry["const"] not in CANONICAL_EVENTS:
                errors.append(f"event_name const '{entry['const']}' is not a canonical event")
        else:
            errors.append(f"unknown mapping target '{target}'")
    return errors


def _validate_entry(target: str, entry: Any, available: set[str]) -> list[str]:
    if not isinstance(entry, dict):
        return [f"mapping for '{target}' must be an object with 'column' or 'const'"]
    has_column = "column" in entry
    has_const = "const" in entry
    if has_column == has_const:
        return [f"mapping for '{target}' must have exactly one of 'column' or 'const'"]
    if has_column:
        column = entry["column"]
        if not isinstance(column, str) or not column.strip():
            return [f"mapping column for '{target}' must be a non-empty string"]
        if column not in available:
            return [f"mapping column '{column}' for '{target}' does not exist in the file"]
    elif entry["const"] is None:
        return [f"mapping const for '{target}' must not be null"]
    return []


def extract_value(row: dict[str, Any], entry: dict[str, Any]) -> Any:
    if "const" in entry:
        return entry["const"]
    current: Any = row
    for part in entry["column"].split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    for symbol in ("$", "€", "£", ",", "%", " "):
        text = text.replace(symbol, "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def coerce_integer(value: Any) -> int | None:
    number = coerce_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def build_events(rows: list[dict[str, Any]], mapping: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Map rows to canonical ingest payloads. Returns (events, issues).

    Events are CommerceEventIngest-shaped dicts tagged with the 1-based source
    row of their first contributing row. Issues carry 1-based data row numbers
    for user-facing error reports.
    """
    units: list[list[tuple[int, dict[str, Any]]]] = []
    if "items" in mapping:
        buckets: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for source_row, row in enumerate(rows, start=1):
            order_entry = mapping.get("order_id")
            key = str(extract_value(row, order_entry) or "").strip() if order_entry else ""
            buckets.setdefault(key, []).append((source_row, row))
        units = list(buckets.values())
    else:
        units = [[(source_row, row)] for source_row, row in enumerate(rows, start=1)]

    events: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for group in units:
        payload, row_issues = _build_one(group, mapping)
        if payload is not None:
            events.append({"source_row": group[0][0], "payload": payload})
        issues.extend({"row": row, "message": message} for row, message in row_issues)
    return events, issues


def _build_one(row_group: list[tuple[int, dict[str, Any]]], mapping: dict[str, Any]) -> tuple[dict[str, Any] | None, list[tuple[int, str]]]:
    first_source_row, first_row = row_group[0]
    issues: list[tuple[int, str]] = []

    name_entry = mapping.get("event_name")
    event_name = str(extract_value(first_row, name_entry) or "").strip() if name_entry else ""
    if not event_name:
        issues.append((first_source_row, "event_name is required"))
    elif event_name not in CANONICAL_EVENTS:
        issues.append((first_source_row, f"event_name '{event_name}' is not a canonical event"))

    order_entry = mapping.get("order_id")
    order_id = str(extract_value(first_row, order_entry) or "").strip() if order_entry else ""
    if not order_id:
        issues.append((first_source_row, "order_id is required"))

    revenue = 0.0
    revenue_entry = mapping.get("revenue")
    raw_revenue = extract_value(first_row, revenue_entry) if revenue_entry else None
    if raw_revenue is not None and str(raw_revenue).strip() != "":
        parsed = coerce_number(raw_revenue)
        if parsed is None:
            issues.append((first_source_row, f"revenue '{raw_revenue}' is not a number"))
        else:
            revenue = parsed

    currency = "USD"
    currency_entry = mapping.get("currency")
    raw_currency = extract_value(first_row, currency_entry) if currency_entry else None
    if raw_currency is not None and str(raw_currency).strip():
        currency = str(raw_currency).strip().upper()

    customer_id: str | None = None
    customer_entry = mapping.get("customer_id")
    raw_customer = extract_value(first_row, customer_entry) if customer_entry else None
    if raw_customer is not None and str(raw_customer).strip():
        customer_id = str(raw_customer).strip()

    occurred_at: str | None = None
    occurred_entry = mapping.get("occurred_at")
    raw_occurred = extract_value(first_row, occurred_entry) if occurred_entry else None
    if raw_occurred is not None and str(raw_occurred).strip() != "":
        parsed_occurred = coerce_datetime(raw_occurred)
        if parsed_occurred is None:
            issues.append((first_source_row, f"occurred_at '{raw_occurred}' is not a recognized date"))
        else:
            occurred_at = parsed_occurred.isoformat()

    items: list[dict[str, Any]] = []
    item_mapping = mapping.get("items")
    if item_mapping:
        for source_row, row in row_group:
            item, item_issues = _build_item(row, item_mapping, source_row)
            issues.extend(item_issues)
            if item is not None:
                items.append(item)

    if issues:
        return None, issues
    payload: dict[str, Any] = {
        "order_id": order_id,
        "revenue": revenue,
        "currency": currency,
        "metadata": {"source_row": first_source_row},
    }
    if customer_id:
        payload["customer_id"] = customer_id
    if occurred_at:
        payload["occurred_at"] = occurred_at
    if items:
        payload["items"] = items
    return {"event_name": event_name, "payload": payload}, []


def _build_item(row: dict[str, Any], item_mapping: dict[str, Any], source_row: int) -> tuple[dict[str, Any] | None, list[tuple[int, str]]]:
    raw: dict[str, Any] = {}
    for target in ITEM_FIELDS:
        entry = item_mapping.get(target)
        raw[target] = extract_value(row, entry) if entry else None
    if all(value is None or str(value).strip() == "" for value in raw.values()):
        return None, []

    item: dict[str, Any] = {}
    issues: list[tuple[int, str]] = []
    if raw["product_id"] is not None and str(raw["product_id"]).strip():
        item["product_id"] = str(raw["product_id"]).strip()
    if raw["name"] is not None and str(raw["name"]).strip():
        item["name"] = str(raw["name"]).strip()
    if raw["price"] is not None and str(raw["price"]).strip() != "":
        price = coerce_number(raw["price"])
        if price is None:
            issues.append((source_row, f"items.price '{raw['price']}' is not a number"))
        else:
            item["price"] = price
    if raw["quantity"] is not None and str(raw["quantity"]).strip() != "":
        quantity = coerce_integer(raw["quantity"])
        if quantity is None:
            issues.append((source_row, f"items.quantity '{raw['quantity']}' is not an integer"))
        else:
            item["quantity"] = quantity
    if issues:
        return None, issues
    return item or None, []
