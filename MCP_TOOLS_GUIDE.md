# Model Context Protocol (MCP) — Commerce, Payment & Risk Tools Reference

This guide provides a comprehensive reference for all MCP tools exposed by **SaaS MCP**. It explains how autonomous AI agents, **Claude Desktop**, and **Cursor IDE** interact with commerce analytics, universal payment processing, interbank switches, and risk sentinel tools.

---

## 1. Architectural Principles

According to `AGENTS.md` and the SaaS MCP core contract:
* **Keep MCP tools thin**: MCP tools are transport adapters that validate input, resolve tenant context, and delegate to backend services (`AnalyticsService`, `PaymentService`, `RiskAssessmentService`).
* **Provider-Neutral Contract**: Tools expose the universal commerce and payment model. No provider-specific (e.g. Stripe-only or Shopify-only) tools are permitted.
* **Tenant Isolation**: Every tool call is scoped to the authenticated organization's session. Cross-tenant access is physically impossible.
* **Structured Outputs**: All tools return typed JSON matching Pydantic schemas. Direct arbitrary SQL is strictly prohibited.

---

## 2. Tool Directory Overview

The platform exposes **21 Tools** categorized into three specialized domains:

```
                          ┌──────────────────────────┐
                          │     SaaS MCP Server      │
                          └─────────────┬────────────┘
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│  Commerce Tools  │           │  Payment Tools   │           │   Risk & Switch  │
│  (7 Tools)       │           │  (8 Tools)       │           │   (6 Tools)      │
└──────────────────┘           └──────────────────┘           └──────────────────┘
```

---

## 3. Commerce Analytics Tools

These tools enable LLMs to analyze digital commerce performance, storefront connections, order metrics, and SKU velocity.

### 3.1 `list_commerce_sources`
Lists all connected storefronts, commerce platforms, and data warehouses configured for the tenant.
* **Input Schema**: None
* **Sample LLM Call**:
  ```json
  {}
  ```
* **Returns**: Array of source objects containing `id`, `name`, `provider` (e.g., `shopify`, `bank-statement`, `custom-warehouse`), `store_url`, and `status`.

### 3.2 `register_commerce_source`
Registers a new commerce data source or bank feed under the organization.
* **Input Schema**:
  * `name` *(string, required)*: Descriptive label for the source.
  * `source` *(string, required)*: System identifier (e.g. `shopify-us`, `sbi-bank-feed`).
  * `store_url` *(string, required)*: Target URL or endpoint.
* **Sample LLM Call**:
  ```json
  {
    "name": "Flagship Shopify Store",
    "source": "shopify-main",
    "store_url": "https://brand.myshopify.com"
  }
  ```

### 3.3 `ingest_canonical_event`
Directly pushes a platform-neutral canonical commerce event into the ingestion pipeline.
* **Input Schema**:
  * `storefront_id` *(integer, required)*: Target storefront ID.
  * `event_name` *(string, required)*: Canonical event (`purchase`, `order_created`, `refund`, `payment_failed`, etc.).
  * `payload` *(object, required)*: Event properties (`revenue`, `order_id`, `customer_id`, `items`).
* **Sample LLM Call**:
  ```json
  {
    "storefront_id": 1,
    "event_name": "purchase",
    "payload": {
      "order_id": "ORD-9921",
      "revenue": 149.99,
      "currency": "USD",
      "customer_id": "cust_123@example.com"
    }
  }
  ```

### 3.4 `get_analytics_summary`
Returns high-level commercial health KPIs for a date range.
* **Input Schema**:
  * `start_date` *(string, optional)*: ISO date (`YYYY-MM-DD`).
  * `end_date` *(string, optional)*: ISO date (`YYYY-MM-DD`).
* **Returns**:
  ```json
  {
    "revenue": 245900.50,
    "purchases": 3210,
    "aov": 76.60,
    "unique_customers": 2840,
    "currency": "USD"
  }
  ```

### 3.5 `get_top_products`
Surfaces the best-performing SKUs ranked by revenue or units sold.
* **Input Schema**:
  * `limit` *(integer, default 10)*: Max products to return.
  * `start_date` *(string, optional)*: ISO date.
  * `end_date` *(string, optional)*: ISO date.
* **Returns**: List of products with `product_id`, `name`, `quantity`, and `gross_revenue`.

### 3.6 `get_customer_metrics`
Calculates retention rates, repeat buyer ratios, and customer lifetime value indications.
* **Input Schema**: Date range parameters (`start_date`, `end_date`).
* **Returns**: Metrics detailing `total_customers`, `repeat_customers`, `repeat_rate`, and `churn_risk_segment`.

### 3.7 `get_refund_summary`
Analyzes return and refund velocity, highlighting product defect trends and revenue leakage.
* **Input Schema**: Date range parameters (`start_date`, `end_date`).
* **Returns**: Total refunded volume, refund rate percentage, and breakdown by return reasons.

---

## 4. Universal Payment & Revenue-Recovery Tools

These tools interact with the normalized universal payment model (`Payment`, `PaymentAttempt`, `RecoveryCase`, `Refund`).

### 4.1 `get_payment_metrics`
Evaluates aggregate transaction settlement health across all processors.
* **Input Schema**: `start_date`, `end_date`.
* **Returns**:
  ```json
  {
    "total_attempts": 5120,
    "successful_attempts": 4820,
    "failed_attempts": 300,
    "success_rate": 0.9414,
    "succeeded_amount": 389400.00,
    "failed_amount": 24200.00,
    "currency": "USD"
  }
  ```

### 4.2 `get_payment_failures`
Returns granular diagnostic records for failed transactions.
* **Input Schema**:
  * `limit` *(integer, 1-200, default 50)*: Number of failure records.
  * `start_date`, `end_date` *(optional)*.
* **Returns**: List of failures including `payment_ref`, `order_id`, `failure_code` (e.g. `INSUFFICIENT_FUNDS`, `RETURN_REVERSED`), `failure_reason`, and customer identifier.

### 4.3 `get_payment_recovery`
Tracks automated dunning and payment recovery case outcomes.
* **Input Schema**: `start_date`, `end_date`.
* **Returns**: Total recovery attempts, recovered revenue amount, and recovery rate percentage.

### 4.4 `get_revenue_at_risk`
Identifies unrecovered revenue currently trapped in open failure states.
* **Input Schema**: None (calculates real-time open exposure).
* **Returns**: Open failure counts, estimated recoverable balance, and critical age buckets (0-24h, 24-72h, >72h).

### 4.5 `get_customer_payment_history`
Returns a longitudinal payment history for a customer across all attempts and channels.
* **Input Schema**: `customer_id` *(string, required)*.
* **Returns**: Chronological payment events, successful settlements, refunds, and past failures.

### 4.6 `get_transaction_lifecycle`
Reconstructs the full end-to-end timeline for an order.
* **Input Schema**: `order_id` *(string, required)*.
* **Returns**: Ordered event chain (`order_created` $\to$ `payment_attempted` $\to$ `payment_succeeded` $\to$ `reversal_linked`).

### 4.7 `get_revenue_metrics` & 4.8 `get_order_metrics`
Provide breakdown metrics by currency, payment channel, and fulfillment status.

---

## 5. Risk, Interbank Switch & Card Network Tools

These tools expose the high-performance Risk Sentinel, real-time card authorization middleware (<45ms SLA), and the multi-format statement ingestor.

### 5.1 `get_system_lens`
Auto-profiles the organization's transaction corpus and determines whether the workspace operates as **Commerce Analytics** or **Bank/Card Switch**.
* **Input Schema**: None.
* **Returns**:
  ```json
  {
    "detected_mode": "BANK_NETWORK",
    "confidence_score": 0.94,
    "recommended_lens": "BANK_NETWORK",
    "rationale": "94% of transactions represent interbank switch rails (ATM, UPI, POS Card Swipe) with active RRN reversal reconciliations.",
    "active_banking_rails": ["ATM", "UPI", "CARD_SWIPE"],
    "has_reversals": true
  }
  ```

### 5.2 `get_risk_assessment`
Calculates systemic failure rates, channel breakdowns, and phantom reversal risks.
* **Input Schema**:
  * `start_date`, `end_date` *(optional)*.
  * `channel` *(optional)*: Filter by rail (`ATM`, `CARD_SWIPE`, `UPI`, `ONLINE_CARD`, `TRANSFER`).
* **Returns**:
  ```json
  {
    "total_transactions": 1420,
    "overall_failure_rate": 0.082,
    "overall_risk_score": 38.5,
    "risk_tier": "ELEVATED",
    "highest_risk_channel": "ATM",
    "highest_risk_entity": "SBI ATM Kothrud Pune",
    "channel_breakdown": [
      { "channel": "ATM", "failure_rate_percentage": 18.4, "failed_volume": 42000.0 },
      { "channel": "UPI", "failure_rate_percentage": 3.1, "failed_volume": 12400.0 }
    ],
    "phantom_reversals_detected": 4
  }
  ```

### 5.3 `get_high_risk_entities`
Returns the **"Most Failed at Which Name" Leaderboard**, ranking merchants and ATM terminals by failure and reversal volume.
* **Input Schema**:
  * `limit` *(integer, default 20)*: Max entities.
  * `min_failures` *(integer, default 1)*: Minimum failure threshold.
  * `channel` *(string, optional)*: Filter by channel.
* **Returns**: Ranked list of entities with `rank`, `entity_name`, `primary_channel`, `total_attempts`, `failed_count`, `failed_amount`, `risk_score` (0-100), `risk_tier`, and actionable `recommendation`.

### 5.4 `get_entity_risk_dna`
Surfaces deep behavioral decline diagnostics and cross-rail correlation for a specific counterparty.
* **Input Schema**:
  * `entity_name` *(string, required)*: Merchant or ATM name (e.g. `Swiggy`, `SBI ATM Kothrud`).
* **Returns**:
  * `composite_risk_score`: 0-100 risk index.
  * `channel_vulnerabilities`: Multi-rail failure comparison (e.g. `UPI: 42.1%`, `CARD_SWIPE: 1.8%`).
  * `reversal_velocity_cadence`: Reversal lag behavior (e.g. `Immediate switch return` vs `48-72h settlement delay`).
  * `strategic_remediation`: Concrete remediation action.

### 5.5 `evaluate_transaction_risk`
**Real-Time Card Network Integration Middleware** (<45ms SLA). Simulates or executes live screening between card networks (Mastercard/Visa) and issuing banks.
* **Input Schema**:
  * `transaction_ref` *(string, required)*: Unique auth request ID.
  * `entity_name` *(string, required)*: Counterparty merchant or terminal.
  * `amount` *(number, required)*: Transaction amount.
  * `channel` *(string, default "CARD_SWIPE")*: Rail (`ATM`, `CARD_SWIPE`, `UPI`, `ONLINE_CARD`).
  * `card_bin` *(string, optional)*: First 6-8 digits of card PAN.
  * `country_code` *(string, optional)*: ISO country code.
* **Sample Output**:
  ```json
  {
    "transaction_ref": "auth-req-8841",
    "decision": "APPROVE",
    "risk_score": 18.2,
    "risk_tier": "NORMAL",
    "suggested_action": "Route to clearing switch for immediate settlement",
    "evaluated_at": "2026-10-16T15:30:00Z"
  }
  ```

### 5.6 `ingest_statement_file`
Uploads and ingests a bank or card statement file (`.csv`, `.xlsx`, `.xls`, `.pdf`) directly from local filesystem paths.
* **Input Schema**:
  * `file_path` *(string, required)*: Absolute path to the file.
  * `pdf_password` *(string, optional)*: Decryption password for encrypted bank statement PDFs.
* **Features**:
  * Automatically strips sensitive PII/PCI before database insertion.
  * Preserves RRN / UTR reference numbers.
  * Atomically establishes debit-credit reversal links.
* **Returns**:
  ```json
  {
    "filename": "sbi_statement_oct.csv",
    "format_detected": "CSV",
    "rows_parsed": 142,
    "rows_ingested": 142,
    "reversals_linked": 6,
    "total_debit_amount": 184500.0,
    "total_credit_amount": 24200.0,
    "errors": []
  }
  ```

---

## 6. System Resources

MCP resources provide read-only context feeds to attached models:

| Resource URI | Description | MIME Type |
|---|---|---|
| `system://info` | Server name, platform version, environment status, and capabilities. | `application/json` |
| `analytics://summary` | Real-time organization revenue snapshot and payment success rate. | `application/json` |

---

## 7. Claude Desktop & Cursor IDE Example Queries

Once configured, models can answer natural language prompts by orchestrating these tools:

#### Example Prompt 1 (Risk & Reversal Analysis):
> *"Show me our worst performing merchants and ATM terminals this month, and check if any have phantom reversal loops."*
* **Model action**: Calls `get_high_risk_entities(limit=10)` $\to$ inspects `phantom_reversal_risk` $\to$ calls `get_entity_risk_dna(entity_name="...")` for root cause explanation.

#### Example Prompt 2 (Statement Ingestion):
> *"Ingest my October bank statement at `D:\statements\sbi_october.pdf` using password `15081995`."*
* **Model action**: Calls `ingest_statement_file(file_path="D:\\statements\\sbi_october.pdf", pdf_password="15081995")` $\to$ returns sanitized rows, total debits, and linked reversals.

#### Example Prompt 3 (Real-Time Authorization Check):
> *"We received an authorization request from Swiggy for $85.00 over UPI. Should we approve or decline?"*
* **Model action**: Calls `evaluate_transaction_risk(transaction_ref="auth-101", entity_name="Swiggy", channel="UPI", amount=85.00)` $\to$ answers with `APPROVE` and failure risk score.
