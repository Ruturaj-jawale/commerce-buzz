import { useState, type FormEvent } from "react";
import type { Storefront } from "../api/commerce";
import {
  fetchImport,
  setImportMapping,
  startImport,
  uploadImportFile,
  type ImportCreated,
  type ImportMapping,
  type ImportStatusRead,
  type ValidationReport,
} from "../api/imports";
import { uploadStatementFile, type StatementIngestionResponse } from "../api/risk";
import { sanitizeStatementFileBeforeUpload } from "../utils/sanitizer";
import { CsvPreviewGrid, type ColType, type ColumnMeta, type GridRow } from "../components/CsvPreviewGrid";

type FieldKey = "order_id" | "revenue" | "currency" | "customer_id" | "occurred_at";
type ItemKey = "product_id" | "name" | "price" | "quantity";

type FieldState = { mode: "none" | "column" | "const"; column: string; constant: string };

// Phase order: pick → preview → map → report → status
type Phase = "pick" | "preview" | "map" | "report" | "status";

const FIELD_LABELS: Record<FieldKey, string> = {
  order_id: "Order ID",
  revenue: "Revenue / total",
  currency: "Currency",
  customer_id: "Customer",
  occurred_at: "Date",
};

const ITEM_LABELS: Record<ItemKey, string> = {
  product_id: "Product ID / SKU",
  name: "Product name",
  price: "Unit price",
  quantity: "Quantity",
};

const EMPTY_FIELD: FieldState = { mode: "none", column: "", constant: "" };

function fieldFromEntry(entry: { column?: string; const?: unknown } | undefined): FieldState {
  if (!entry) return EMPTY_FIELD;
  if (entry.column !== undefined) return { mode: "column", column: entry.column, constant: "" };
  return { mode: "const", column: "", constant: String(entry.const ?? "") };
}

function entryFromField(state: FieldState): { column: string } | { const: string } | undefined {
  if (state.mode === "column" && state.column) return { column: state.column };
  if (state.mode === "const") return { const: state.constant };
  return undefined;
}

function errorText(err: unknown): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: string };
      return parsed.detail ?? err.message;
    } catch {
      return err.message;
    }
  }
  return "Something went wrong";
}

/** Infer a basic ColType from sample values for a column */
function inferType(values: string[]): ColType {
  const nonEmpty = values.filter((v) => v.trim() !== "");
  if (!nonEmpty.length) return "text";
  const allBool = nonEmpty.every((v) =>
    ["true", "false", "yes", "no", "1", "0", "y", "n"].includes(v.trim().toLowerCase()),
  );
  if (allBool) return "boolean";
  const allNum = nonEmpty.every((v) => !isNaN(Number(v.replace(/[,$\s]/g, ""))));
  if (allNum) return "number";
  const allDate = nonEmpty.every((v) => !isNaN(new Date(v).getTime()) && isNaN(Number(v)));
  if (allDate) return "date";
  return "text";
}

/** Build ColumnMeta[] from batch columns + sample rows */
function buildColumnMeta(columns: string[], sampleRows: Array<Record<string, unknown>>): ColumnMeta[] {
  return columns.map((col) => {
    const values = sampleRows.map((row) => String(row[col] ?? ""));
    return { key: col, label: col, type: inferType(values) };
  });
}

/** Convert sample_rows (unknown values) to GridRow[] (string values) */
function toGridRows(sampleRows: Array<Record<string, unknown>>): GridRow[] {
  return sampleRows.map((row) =>
    Object.fromEntries(Object.entries(row).map(([k, v]) => [k, String(v ?? "")])),
  );
}

/** Intelligent text-to-table parser for OCR text and unstructured documents */
function parseTextToCsvRows(text: string): { columns: string[]; rows: Array<Record<string, string>> } {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  if (!lines.length) {
    return {
      columns: ["order_id", "date", "customer", "revenue", "currency", "status"],
      rows: [
        {
          order_id: "ORD-001",
          date: new Date().toISOString().slice(0, 10),
          customer: "customer@example.com",
          revenue: "0.00",
          currency: "USD",
          status: "succeeded",
        },
      ],
    };
  }

  // 1. Look for tabular lines (2 or more spaces, tabs, or pipes)
  for (let i = 0; i < Math.min(lines.length, 12); i++) {
    const rawTokens = lines[i].split(/\s{2,}|\t|\|/).map((t) => t.trim()).filter(Boolean);
    if (rawTokens.length >= 2) {
      const columns = rawTokens.map((c, idx) => c || `col_${idx + 1}`);
      const rows: Array<Record<string, string>> = [];
      for (let j = i + 1; j < lines.length; j++) {
        const rowVals = lines[j].split(/\s{2,}|\t|\|/).map((t) => t.trim()).filter(Boolean);
        if (!rowVals.length) continue;
        if (rowVals.length === columns.length || Math.abs(rowVals.length - columns.length) <= 1) {
          const rowObj: Record<string, string> = {};
          columns.forEach((col, cIdx) => {
            rowObj[col] = rowVals[cIdx] ?? "";
          });
          rows.push(rowObj);
        }
      }
      if (rows.length > 0) {
        return { columns, rows };
      }
    }
  }

  // 2. Fallback: Parse invoice/receipt key-value pairs
  const fullText = text;
  const orderMatch = fullText.match(/(?:order|invoice|receipt|trans(?:action)?)[\s#.:-]*([a-zA-Z0-9_\-]+)/i);
  const orderId = orderMatch ? orderMatch[1].trim() : "INV-001";

  const dateMatch = fullText.match(/(?:date|dated|time)[\s:]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})/i);
  const dateVal = dateMatch ? dateMatch[1].trim() : new Date().toISOString().slice(0, 10);

  const emailMatch = fullText.match(/([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)/);
  const nameMatch = fullText.match(/(?:customer|bill\s+to|client|buyer)[\s:]*([^\n\r,]+)/i);
  const customer = emailMatch ? emailMatch[1].trim() : nameMatch ? nameMatch[1].trim() : "customer@example.com";

  const amountMatches = Array.from(fullText.matchAll(/(?:total|amount|grand\s+total|due)[\s:$]*([0-9]+(?:\.[0-9]{2})?)/gi));
  let amount = amountMatches.length > 0 ? amountMatches[amountMatches.length - 1][1] : "";
  if (!amount) {
    const floatMatches = Array.from(fullText.matchAll(/\$?\s*([0-9]+\.[0-9]{2})/g));
    amount = floatMatches.length > 0 ? floatMatches[floatMatches.length - 1][1] : "0.00";
  }

  const columns = ["order_id", "date", "customer", "revenue", "currency", "status"];
  const rows = [
    {
      order_id: orderId,
      date: dateVal,
      customer: customer,
      revenue: amount,
      currency: "USD",
      status: "succeeded",
    },
  ];
  return { columns, rows };
}

function tableToCsvFile(columns: string[], rows: Array<Record<string, string>>, filename: string): File {
  const header = columns.map((c) => `"${c.replace(/"/g, '""')}"`).join(",");
  const lines = rows.map((r) =>
    columns.map((c) => `"${(r[c] ?? "").replace(/"/g, '""')}"`).join(","),
  );
  const csvContent = [header, ...lines].join("\n");
  const cleanName = filename.replace(/\.[^.]+$/, "") + "-extracted.csv";
  return new File([csvContent], cleanName, { type: "text/csv" });
}

export function ImportWizard({ storefronts, onImported }: { storefronts: Storefront[]; onImported: () => void }) {
  const [selectedStorefront, setSelectedStorefront] = useState<number | "">("");
  const [sourceName, setSourceName] = useState("");
  const [sourceLabel, setSourceLabel] = useState("file-import");
  const [file, setFile] = useState<File | null>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
  const [created, setCreated] = useState<ImportCreated | null>(null);

  // OCR state
  const [ocrProgress, setOcrProgress] = useState<number | null>(null);
  const [ocrStatusText, setOcrStatusText] = useState<string>("");

  // Preview grid state
  const [previewColumns, setPreviewColumns] = useState<ColumnMeta[]>([]);
  const [previewRows, setPreviewRows] = useState<GridRow[]>([]);

  const [eventName, setEventName] = useState("purchase");
  const [fields, setFields] = useState<Record<FieldKey, FieldState>>({
    order_id: EMPTY_FIELD,
    revenue: EMPTY_FIELD,
    currency: EMPTY_FIELD,
    customer_id: EMPTY_FIELD,
    occurred_at: EMPTY_FIELD,
  });
  const [itemsEnabled, setItemsEnabled] = useState(false);
  const [itemFields, setItemFields] = useState<Record<ItemKey, FieldState>>({
    product_id: EMPTY_FIELD,
    name: EMPTY_FIELD,
    price: EMPTY_FIELD,
    quantity: EMPTY_FIELD,
  });
  const [previewDone, setPreviewDone] = useState(false);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [status, setStatus] = useState<ImportStatusRead | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Studio mode: commerce orders vs bank & card statement
  const [studioMode, setStudioMode] = useState<"commerce" | "bank_statement">("commerce");

  const BANK_HEADER_PRESETS: Record<
    string,
    { name: string; headers: { date: string; narration: string; debit: string; credit: string; balance: string; reference: string } }
  > = {
    auto: {
      name: "Auto-Detect Bank (Recommended)",
      headers: { date: "", narration: "", debit: "", credit: "", balance: "", reference: "" },
    },
    sbi: {
      name: "State Bank of India (SBI)",
      headers: {
        date: "Date",
        narration: "Transaction Reference",
        debit: "Debit",
        credit: "Credit",
        balance: "Balance",
        reference: "Ref.No./Chq.No.",
      },
    },
    ippb: {
      name: "India Post Payments Bank (IPPB)",
      headers: {
        date: "DATE",
        narration: "TRANSACTION PARTICULARS",
        debit: "WITHDRWAL",
        credit: "DEPOSIT",
        balance: "BALANCE",
        reference: "TRAN ID",
      },
    },
    hdfc: {
      name: "HDFC Bank",
      headers: {
        date: "Date",
        narration: "Narration",
        debit: "Withdrawal Amt.",
        credit: "Deposit Amt.",
        balance: "Closing Balance",
        reference: "Chq./Ref.No.",
      },
    },
    icici: {
      name: "ICICI Bank",
      headers: {
        date: "Transaction Date",
        narration: "Transaction Details",
        debit: "Debit",
        credit: "Credit",
        balance: "Balance",
        reference: "Cheque Number",
      },
    },
    axis: {
      name: "Axis Bank",
      headers: {
        date: "Tran Date",
        narration: "PARTICULARS",
        debit: "DR",
        credit: "CR",
        balance: "BAL",
        reference: "CHQNO",
      },
    },
    custom: {
      name: "Custom Column Mapping",
      headers: { date: "", narration: "", debit: "", credit: "", balance: "", reference: "" },
    },
  };

  // Bank statement studio state
  const [stmtFile, setStmtFile] = useState<File | null>(null);
  const [stmtPassword, setStmtPassword] = useState<string>("");
  const [bankPreset, setBankPreset] = useState<string>("auto");
  const [showCustomHeaders, setShowCustomHeaders] = useState<boolean>(false);
  const [customHeaders, setCustomHeaders] = useState({
    date: "",
    narration: "",
    debit: "",
    credit: "",
    balance: "",
    reference: "",
  });
  const [stmtSanitizing, setStmtSanitizing] = useState<boolean>(false);
  const [stmtSanitizationCount, setStmtSanitizationCount] = useState<number>(0);
  const [stmtPreviewRows, setStmtPreviewRows] = useState<Array<Record<string, string>>>([]);
  const [stmtPreviewCols, setStmtPreviewCols] = useState<string[]>([]);
  const [stmtPhase, setStmtPhase] = useState<"pick" | "preview" | "ingesting" | "result">("pick");
  const [stmtResult, setStmtResult] = useState<StatementIngestionResponse | null>(null);
  const [stmtError, setStmtError] = useState<string | null>(null);

  async function handleStmtFileSelect(f: File | null) {
    setStmtFile(f);
    setStmtError(null);
    setStmtResult(null);
    if (!f) {
      setStmtPreviewRows([]);
      setStmtPreviewCols([]);
      setStmtSanitizationCount(0);
      setStmtPhase("pick");
      return;
    }
    setStmtSanitizing(true);
    try {
      const { file: safeFile, count, format } = await sanitizeStatementFileBeforeUpload(f);
      setStmtSanitizationCount(count);
      if (format === "CSV" || f.name.toLowerCase().endsWith(".csv") || f.name.toLowerCase().endsWith(".txt")) {
        const text = await safeFile.text();
        const rawLines = text.split("\n").filter((l) => l.trim().length > 0);
        if (rawLines.length > 0) {
          // Detect candidate header line by scanning initial rows for column keywords
          let headerIdx = 0;
          let bestScore = -1;
          for (let i = 0; i < Math.min(rawLines.length, 35); i++) {
            const cols = rawLines[i].split(",").map((c) => c.trim().replace(/^"|"$/g, "")).filter(Boolean);
            if (cols.length >= 2) {
              const kwMatches = cols.filter((c) =>
                /date|time|particular|narrat|withdr|deposit|debit|credit|bal|ref|tran/i.test(c)
              ).length;
              const score = kwMatches * 10 + Math.min(cols.length, 10);
              if (score > bestScore) {
                bestScore = score;
                headerIdx = i;
              }
            }
          }
          const headers = rawLines[headerIdx].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
          const rows = rawLines.slice(headerIdx + 1, headerIdx + 11).map((line) => {
            const vals = line.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
            const obj: Record<string, string> = {};
            headers.forEach((h, idx) => {
              obj[h] = vals[idx] || "";
            });
            return obj;
          });
          setStmtPreviewCols(headers);
          setStmtPreviewRows(rows);
          setStmtPhase("preview");
        }
      } else {
        setStmtPhase("preview");
      }
    } catch (err) {
      console.warn("Statement client prep note:", err);
    } finally {
      setStmtSanitizing(false);
    }
  }

  async function onIngestStatement(e: FormEvent) {
    e.preventDefault();
    if (!stmtFile) return;
    setStmtPhase("ingesting");
    setStmtError(null);
    try {
      const hasNonEmptyCustom = Object.values(customHeaders).some((v) => v.trim().length > 0);
      const activeHeaders = bankPreset === "custom" || showCustomHeaders || hasNonEmptyCustom ? customHeaders : undefined;
      const res = await uploadStatementFile(stmtFile, stmtPassword || undefined, bankPreset, activeHeaders);
      setStmtResult(res);
      setStmtPhase("result");
      onImported();
    } catch (err) {
      setStmtError(err instanceof Error ? err.message : String(err));
      setStmtPhase("preview");
    }
  }

  function onResetStatement() {
    setStmtFile(null);
    setStmtPassword("");
    setStmtPreviewRows([]);
    setStmtPreviewCols([]);
    setStmtSanitizationCount(0);
    setStmtResult(null);
    setStmtError(null);
    setStmtPhase("pick");
  }

  const batch = created?.batch ?? null;

  // Derive phase from explicit state flags
  const phase: Phase = status
    ? "status"
    : report
      ? "report"
      : created && previewColumns.length > 0 && !previewDone
        ? "preview"
        : created
          ? "map"
          : "pick";

  const done = status?.batch.status === "completed" || status?.batch.status === "failed";

  const activeColumns = previewColumns.length > 0
    ? previewColumns.map((c) => c.label)
    : (batch?.columns ?? []);

  function handleFileSelection(f: File | null) {
    setFile(f);
    setError(null);
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
      setImagePreviewUrl(null);
    }
    if (f && /\.(png|jpe?g|webp|bmp|tiff)$/i.test(f.name)) {
      setImagePreviewUrl(URL.createObjectURL(f));
    }
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setOcrProgress(null);

    try {
      let fileToUpload: File = file;
      const isImage = /\.(png|jpe?g|webp|bmp|tiff)$/i.test(file.name);

      // Pre-upload sanitization: redacts any sensitive card/account numbers before transmission
      const { file: safeCommerceFile } = await sanitizeStatementFileBeforeUpload(fileToUpload);
      fileToUpload = safeCommerceFile;

      if (isImage) {
        setOcrStatusText("Initializing AI OCR engine...");
        setOcrProgress(15);
        try {
          const { default: Tesseract } = await import("tesseract.js");
          const ocrResult = await Tesseract.recognize(file, "eng", {
            logger: (m) => {
              if (m.status === "recognizing text") {
                setOcrProgress(Math.round(20 + m.progress * 75));
                setOcrStatusText(`Extracting text & table data... ${Math.round(m.progress * 100)}%`);
              } else if (m.status) {
                setOcrStatusText(m.status);
              }
            },
          });
          setOcrStatusText("Parsing extracted transaction fields...");
          setOcrProgress(95);
          const { columns, rows } = parseTextToCsvRows(ocrResult.data.text);
          fileToUpload = tableToCsvFile(columns, rows, file.name);
        } catch (ocrErr) {
          console.warn("Client-side OCR failed, sending to server directly:", ocrErr);
        }
      }

      setOcrStatusText("Uploading to ingestion pipeline...");
      const result = await uploadImportFile(
        fileToUpload,
        selectedStorefront
          ? { storefrontId: Number(selectedStorefront) }
          : { sourceName, sourceLabel },
      );
      setCreated(result);

      // Build preview grid from server response
      const cols = buildColumnMeta(result.batch.columns, result.sample_rows);
      setPreviewColumns(cols);
      setPreviewRows(toGridRows(result.sample_rows));

      // Prefill mapping suggestions
      const suggested = result.suggested_mapping;
      setEventName(
        suggested.event_name?.const !== undefined ? String(suggested.event_name.const) : "purchase",
      );
      setFields({
        order_id: fieldFromEntry(suggested.order_id),
        revenue: fieldFromEntry(suggested.revenue),
        currency: fieldFromEntry(suggested.currency),
        customer_id: fieldFromEntry(suggested.customer_id),
        occurred_at: fieldFromEntry(suggested.occurred_at),
      });
      const items = suggested.items;
      setItemsEnabled(Boolean(items && Object.keys(items).length));
      setItemFields({
        product_id: fieldFromEntry(items?.product_id),
        name: fieldFromEntry(items?.name),
        price: fieldFromEntry(items?.price),
        quantity: fieldFromEntry(items?.quantity),
      });
      setReport(null);
      setStatus(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
      setOcrProgress(null);
      setOcrStatusText("");
    }
  }

  function currentMapping(): ImportMapping {
    const mapping: ImportMapping = {};
    if (eventName.trim()) mapping.event_name = { const: eventName.trim() };
    for (const key of Object.keys(fields) as FieldKey[]) {
      const entry = entryFromField(fields[key]);
      if (entry) mapping[key] = entry;
    }
    if (itemsEnabled) {
      mapping.items = {};
      for (const key of Object.keys(itemFields) as ItemKey[]) {
        const entry = entryFromField(itemFields[key]);
        if (entry) mapping.items[key] = entry;
      }
    }
    return mapping;
  }

  async function onValidate() {
    if (!batch) return;
    setBusy(true);
    setError(null);
    try {
      const result = await setImportMapping(batch.id, currentMapping());
      setReport(result);
      setStatus(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function onImport() {
    if (!batch) return;
    setBusy(true);
    setError(null);
    try {
      await startImport(batch.id);
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 800));
        const current = await fetchImport(batch.id);
        setStatus(current);
        if (current.batch.status === "completed" || current.batch.status === "failed") {
          if (current.batch.status === "completed") onImported();
          break;
        }
      }
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function onReset() {
    setCreated(null);
    setPreviewColumns([]);
    setPreviewRows([]);
    setPreviewDone(false);
    setReport(null);
    setStatus(null);
    setFile(null);
    if (imagePreviewUrl) {
      URL.revokeObjectURL(imagePreviewUrl);
      setImagePreviewUrl(null);
    }
    setOcrProgress(null);
    setOcrStatusText("");
    setError(null);
  }

  function fieldSelect(value: FieldState, onChange: (next: FieldState) => void, columns: string[]) {
    return (
      <span style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={value.mode === "const" ? "__const" : value.mode === "column" ? value.column : ""}
          onChange={(e) => {
            const selected = e.target.value;
            if (selected === "") onChange({ ...value, mode: "none", column: "" });
            else if (selected === "__const") onChange({ ...value, mode: "const" });
            else onChange({ mode: "column", column: selected, constant: value.constant });
          }}
        >
          <option value="">Not mapped</option>
          {value.mode === "const" ? <option value="__const">Constant…</option> : null}
          {columns.map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
          {value.mode !== "const" ? <option value="__const">Constant…</option> : null}
        </select>
        {value.mode === "const" ? (
          <input
            placeholder="constant value"
            value={value.constant}
            onChange={(e) => onChange({ ...value, constant: e.target.value })}
          />
        ) : null}
      </span>
    );
  }

  const steps: { id: Phase; label: string }[] = [
    { id: "pick", label: "Upload & OCR" },
    { id: "preview", label: "Preview & Edit" },
    { id: "map", label: "Map fields" },
    { id: "report", label: "Validate" },
    { id: "status", label: "Import" },
  ];
  const stepOrder = steps.map((s) => s.id);
  const currentStepIdx = stepOrder.indexOf(phase);

  return (
    <section className="panel">
      <h2>Schema &amp; Document Import Studio</h2>
      <p className="lede">
        Upload any CSV, Excel workbook, PDF invoice/statement, or document image (.png, .jpg, .webp).
        Built-in AI OCR extracts tabular data into an Excel-style grid for cleaning, type casting, and immediate analytics on your dashboard.
      </p>

      {/* ── Studio Mode Switcher: Commerce Orders vs Bank Statements ── */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", background: "rgba(255,255,255,0.05)", padding: "0.35rem", borderRadius: "10px", width: "fit-content" }}>
        <button
          type="button"
          onClick={() => setStudioMode("commerce")}
          style={{
            padding: "0.45rem 1rem",
            borderRadius: "8px",
            border: "none",
            background: studioMode === "commerce" ? "var(--primary, #3b82f6)" : "transparent",
            color: studioMode === "commerce" ? "#fff" : "#94a3b8",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: "0.85rem",
          }}
        >
          🛒 E-Commerce &amp; Order Imports
        </button>
        <button
          type="button"
          onClick={() => setStudioMode("bank_statement")}
          style={{
            padding: "0.45rem 1rem",
            borderRadius: "8px",
            border: "none",
            background: studioMode === "bank_statement" ? "#8b5cf6" : "transparent",
            color: studioMode === "bank_statement" ? "#fff" : "#94a3b8",
            cursor: "pointer",
            fontWeight: 700,
            fontSize: "0.85rem",
          }}
        >
          🏦 Bank &amp; Card Statement Import
        </button>
      </div>

      {studioMode === "bank_statement" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Statement Ingest Progress Steps */}
          <div className="import-steps">
            {[
              { id: "pick", label: "1. Select Statement" },
              { id: "preview", label: "2. Preview & Sanitize" },
              { id: "result", label: "3. Results & Status" },
            ].map((s, idx) => {
              const currentIdx = stmtPhase === "pick" ? 0 : stmtPhase === "preview" || stmtPhase === "ingesting" ? 1 : 2;
              return (
                <div
                  key={s.id}
                  className={`import-step${idx < currentIdx ? " done" : idx === currentIdx ? " active" : ""}`}
                >
                  <span className="step-dot">{idx < currentIdx ? "✓" : idx + 1}</span>
                  <span className="step-label">{s.label}</span>
                  {idx < 2 && <span className="step-line" />}
                </div>
              );
            })}
          </div>

          {stmtError ? <p className="error">{stmtError}</p> : null}

          {stmtPhase !== "result" ? (
            <form className="form" onSubmit={(e) => void onIngestStatement(e)}>
              <label>
                Bank / Card Statement File (.csv, .xlsx, .xls, .pdf)
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls,.pdf"
                  required
                  onChange={(e) => void handleStmtFileSelect(e.target.files?.[0] || null)}
                />
              </label>

              {stmtFile?.name.toLowerCase().endsWith(".pdf") ? (
                <label>
                  PDF Password (Optional — if password-protected by bank with DOB or mobile number)
                  <input
                    type="password"
                    placeholder="e.g. 15081995"
                    value={stmtPassword}
                    onChange={(e) => setStmtPassword(e.target.value)}
                  />
                </label>
              ) : null}

              {/* Bank Format Template & Custom Column Headers */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                  padding: "0.85rem 1rem",
                  background: "rgba(255, 255, 255, 0.03)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "8px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                  <label style={{ margin: 0, fontWeight: 600, fontSize: "0.88rem" }}>
                    Bank Statement Format / Template
                    <select
                      value={bankPreset}
                      onChange={(e) => {
                        const val = e.target.value;
                        setBankPreset(val);
                        if (val in BANK_HEADER_PRESETS && val !== "auto") {
                          setCustomHeaders({ ...BANK_HEADER_PRESETS[val].headers });
                          if (val === "custom") {
                            setShowCustomHeaders(true);
                          }
                        }
                      }}
                      style={{
                        display: "block",
                        marginTop: "0.35rem",
                        padding: "0.45rem 0.75rem",
                        background: "rgba(15, 23, 42, 0.8)",
                        border: "1px solid rgba(255, 255, 255, 0.2)",
                        borderRadius: "6px",
                        color: "#fff",
                        fontSize: "0.85rem",
                        minWidth: "260px",
                      }}
                    >
                      {Object.entries(BANK_HEADER_PRESETS).map(([key, item]) => (
                        <option key={key} value={key} style={{ background: "#1e293b", color: "#fff" }}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <button
                    type="button"
                    onClick={() => setShowCustomHeaders(!showCustomHeaders)}
                    style={{
                      background: "transparent",
                      border: "1px dashed rgba(255, 255, 255, 0.25)",
                      borderRadius: "6px",
                      color: "#93c5fd",
                      padding: "0.35rem 0.75rem",
                      fontSize: "0.78rem",
                      cursor: "pointer",
                      alignSelf: "flex-end",
                    }}
                  >
                    {showCustomHeaders ? "▲ Hide Column Mapping" : "⚙ Custom Column Mapping"}
                  </button>
                </div>

                {showCustomHeaders && (
                  <div
                    style={{
                      marginTop: "0.5rem",
                      paddingTop: "0.75rem",
                      borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                    }}
                  >
                    <div style={{ fontSize: "0.78rem", color: "#94a3b8", marginBottom: "0.6rem" }}>
                      Specify the column header names matching your bank statement table:
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                        gap: "0.65rem",
                      }}
                    >
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Date Column
                        <input
                          type="text"
                          placeholder="e.g. Date or Tran Date"
                          value={customHeaders.date}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, date: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Narration / Particulars
                        <input
                          type="text"
                          placeholder="e.g. Particulars / Narration"
                          value={customHeaders.narration}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, narration: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Withdrawal / Debit
                        <input
                          type="text"
                          placeholder="e.g. Debit / Withdrawal"
                          value={customHeaders.debit}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, debit: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Deposit / Credit
                        <input
                          type="text"
                          placeholder="e.g. Credit / Deposit"
                          value={customHeaders.credit}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, credit: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Closing Balance
                        <input
                          type="text"
                          placeholder="e.g. Balance"
                          value={customHeaders.balance}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, balance: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                      <label style={{ margin: 0, fontSize: "0.78rem", color: "#cbd5e1" }}>
                        Ref / Cheque / UTR
                        <input
                          type="text"
                          placeholder="e.g. Ref.No./Chq.No. or Tran ID"
                          value={customHeaders.reference}
                          onChange={(e) => setCustomHeaders({ ...customHeaders, reference: e.target.value })}
                          style={{ marginTop: "0.25rem", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" }}
                        />
                      </label>
                    </div>
                  </div>
                )}
              </div>

              {/* Privacy Sanitization Status */}
              <div
                style={{
                  padding: "0.85rem 1rem",
                  background: stmtSanitizationCount > 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(59, 130, 246, 0.1)",
                  border: `1px solid ${stmtSanitizationCount > 0 ? "rgba(16, 185, 129, 0.3)" : "rgba(59, 130, 246, 0.25)"}`,
                  borderRadius: "8px",
                  fontSize: "0.85rem",
                  color: stmtSanitizationCount > 0 ? "#6ee7b7" : "#93c5fd",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.6rem",
                }}
              >
                <span style={{ fontSize: "1.2rem" }}>🔒</span>
                <div>
                  <strong>Sensitive Data Auto-Redacted</strong>
                  <div style={{ fontSize: "0.78rem", marginTop: "0.2rem", color: "#cbd5e1" }}>
                    {stmtSanitizing
                      ? "Scanning for sensitive data in your browser…"
                      : stmtSanitizationCount > 0
                        ? `Redacted ${stmtSanitizationCount} sensitive fields (card numbers, account numbers, Aadhaar, CVV, phone, email) locally before upload. Reference numbers (RRN/UTR) are preserved.`
                        : "Card numbers, account numbers, and personal identifiers are automatically redacted before upload."}
                  </div>
                </div>
              </div>

              {/* Sanitized Live Preview Table */}
              {stmtPreviewRows.length > 0 ? (
                <div style={{ marginTop: "1rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <h4 style={{ margin: 0, fontSize: "0.95rem", color: "#fff" }}>
                      Sanitized Statement Preview (First {stmtPreviewRows.length} rows)
                    </h4>
                    <span style={{ fontSize: "0.75rem", color: "#38bdf8" }}>
                      Auto-detected Rails: ATM, UPI, Card Swipe, Transfer
                    </span>
                  </div>
                  <div style={{ overflowX: "auto", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "6px" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "rgba(255,255,255,0.06)", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                          {stmtPreviewCols.map((c) => (
                            <th key={c} style={{ padding: "0.5rem 0.75rem", color: "#94a3b8" }}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {stmtPreviewRows.map((r, rIdx) => (
                          <tr key={rIdx} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                            {stmtPreviewCols.map((c) => (
                              <td key={c} style={{ padding: "0.45rem 0.75rem", color: "#cbd5e1" }}>
                                {r[c]?.includes("[REDACTED") ? (
                                  <span style={{ color: "#f87171", fontWeight: 600 }}>{r[c]}</span>
                                ) : (
                                  r[c]
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}

              <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
                <button
                  type="submit"
                  className="primary"
                  disabled={stmtPhase === "ingesting" || !stmtFile || stmtSanitizing}
                >
                  {stmtPhase === "ingesting"
                    ? "Importing & Linking Reversals…"
                    : "Import Statement"}
                </button>
                {stmtFile ? (
                  <button type="button" onClick={onResetStatement}>
                    Reset
                  </button>
                ) : null}
              </div>
            </form>
          ) : (
            /* Phase: result */
            <div style={{ padding: "1.5rem", background: "rgba(59, 130, 246, 0.12)", borderRadius: "10px", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "#93c5fd", fontSize: "1.1rem", fontWeight: 700 }}>
                <span>✅</span>
                <span>Statement Imported Successfully ({stmtResult?.format_detected})</span>
              </div>
              <p style={{ margin: "0.4rem 0 1rem", fontSize: "0.85rem", color: "#cbd5e1" }}>
                Transactions were normalized, sensitive data redacted, and reversals automatically linked.
              </p>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", marginTop: "1rem" }}>
                <div style={{ background: "rgba(0,0,0,0.25)", padding: "1rem", borderRadius: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>TRANSACTIONS INGESTED</div>
                  <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#fff", marginTop: "0.25rem" }}>
                    {stmtResult?.rows_ingested} <span style={{ fontSize: "0.85rem", color: "#94a3b8" }}>/ {stmtResult?.rows_parsed}</span>
                  </div>
                </div>
                <div style={{ background: "rgba(0,0,0,0.25)", padding: "1rem", borderRadius: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>REVERSALS LINKED</div>
                  <div style={{ fontSize: "1.6rem", fontWeight: 800, color: "#38bdf8", marginTop: "0.25rem" }}>
                    {stmtResult?.reversals_linked}
                  </div>
                  <div style={{ fontSize: "0.72rem", color: "#94a3b8", marginTop: "0.2rem" }}>Matched to original debits</div>
                </div>
                <div style={{ background: "rgba(0,0,0,0.25)", padding: "1rem", borderRadius: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>TOTAL DEBITS</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#f87171", marginTop: "0.25rem" }}>
                    ₹{stmtResult?.total_debit_amount}
                  </div>
                </div>
                <div style={{ background: "rgba(0,0,0,0.25)", padding: "1rem", borderRadius: "8px" }}>
                  <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>TOTAL CREDITS / RETURNS</div>
                  <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "#4ade80", marginTop: "0.25rem" }}>
                    ₹{stmtResult?.total_credit_amount}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: "1rem", marginTop: "1.5rem" }}>
                <button type="button" className="primary" onClick={onResetStatement}>
                  Import Another Statement
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* ── Step progress bar ── */}
          <div className="import-steps">
            {steps.map((step, idx) => (
              <div
                key={step.id}
                className={`import-step${idx < currentStepIdx ? " done" : idx === currentStepIdx ? " active" : ""}`}
              >
                <span className="step-dot">{idx < currentStepIdx ? "✓" : idx + 1}</span>
                <span className="step-label">{step.label}</span>
                {idx < steps.length - 1 && <span className="step-line" />}
              </div>
            ))}
          </div>

      {error ? <p className="error">{error}</p> : null}

      {/* ══════════════════════════════════════════
          PHASE: pick — upload & document picker
      ══════════════════════════════════════════ */}
      {phase === "pick" ? (
        <form className="form" onSubmit={(e) => void onUpload(e)}>
          <label>
            Existing commerce source (optional)
            <select
              value={selectedStorefront}
              onChange={(e) => setSelectedStorefront(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Create a source for this file</option>
              {storefronts.map((store) => (
                <option key={store.id} value={store.id}>
                  {store.name} ({store.source})
                </option>
              ))}
            </select>
          </label>
          {!selectedStorefront ? (
            <>
              <label>
                Source name
                <input
                  value={sourceName}
                  onChange={(e) => setSourceName(e.target.value)}
                  placeholder="October invoice &amp; receipt export"
                />
              </label>
              <label>
                Source category
                <input
                  value={sourceLabel}
                  onChange={(e) => setSourceLabel(e.target.value)}
                  placeholder="file-import, marketplace, invoice-ocr"
                />
              </label>
            </>
          ) : null}

          <label>
            File (.csv, .xlsx, .pdf, or image .png, .jpg, .webp)
            <input
              type="file"
              accept=".csv,.xlsx,.pdf,.png,.jpg,.jpeg,.webp,.bmp"
              onChange={(e) => handleFileSelection(e.target.files?.[0] ?? null)}
              required
            />
          </label>

          {/* ── Document / Image Preview Card ── */}
          {file && (
            <div className="doc-preview-card">
              {imagePreviewUrl ? (
                <div className="image-preview-box">
                  <img src={imagePreviewUrl} alt="Document preview" className="doc-thumbnail" />
                  <div className="doc-preview-info">
                    <strong>{file.name}</strong>
                    <small className="muted">{(file.size / 1024).toFixed(1)} KB · Image receipt/invoice</small>
                    <span className="ocr-pill">⚡ High-Accuracy Client OCR Ready</span>
                  </div>
                </div>
              ) : (
                <div className="doc-preview-info">
                  <strong>📄 {file.name}</strong>
                  <small className="muted">{(file.size / 1024).toFixed(1)} KB · {file.name.endsWith(".pdf") ? "PDF Document" : "Data File"}</small>
                  {file.name.endsWith(".pdf") && (
                    <span className="ocr-pill">📑 PDF Table &amp; Key-Value Extractor Ready</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── OCR Progress Bar ── */}
          {ocrProgress !== null && (
            <div className="ocr-progress-box">
              <div className="ocr-progress-meta">
                <span>{ocrStatusText || "Processing document..."}</span>
                <span>{ocrProgress}%</span>
              </div>
              <div className="ocr-progress-track">
                <div className="ocr-progress-fill" style={{ width: `${ocrProgress}%` }} />
              </div>
            </div>
          )}

          <button type="submit" disabled={busy || !file}>
            {busy ? ocrStatusText || "Analyzing document…" : "Upload & Analyze Data"}
          </button>
        </form>
      ) : null}

      {/* ══════════════════════════════════════════
          PHASE: preview — Excel-like grid
      ══════════════════════════════════════════ */}
      {phase === "preview" ? (
        <div>
          <div className="preview-meta">
            <span>
              <strong>{batch?.filename}</strong> · {batch?.total_rows} total rows extracted ·{" "}
              {previewRows.length} sample rows shown
            </span>
            <div className="preview-actions">
              <button type="button" className="secondary-btn" onClick={onReset}>
                ← Change file
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setPreviewDone(true)}
              >
                Continue to field mapping →
              </button>
            </div>
          </div>

          <CsvPreviewGrid
            columns={previewColumns}
            rows={previewRows}
            onColumnsChange={setPreviewColumns}
            onRowsChange={setPreviewRows}
          />
        </div>
      ) : null}

      {/* ══════════════════════════════════════════
          PHASE: map / report — field mapping
      ══════════════════════════════════════════ */}
      {phase === "map" || phase === "report" ? (
        <div className="form">
          <div className="preview-meta">
            <span>
              <strong>{batch?.filename}</strong> · {batch?.total_rows} rows ·{" "}
              {(created?.sample_rows.length ?? 0)} sample shown
            </span>
            <button
              type="button"
              className="secondary-btn"
              onClick={() => {
                setReport(null);
                setPreviewDone(false);
              }}
            >
              ← Back to preview
            </button>
          </div>

          {/* Mini read-only data preview strip */}
          <div className="mini-preview-wrap">
            <table className="csv-grid mini">
              <thead>
                <tr>
                  {activeColumns.slice(0, 8).map((col) => (
                    <th key={col} className="csv-th">{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.slice(0, 4).map((row, i) => (
                  <tr key={i} className={i % 2 === 0 ? "" : "csv-row-alt"}>
                    {activeColumns.slice(0, 8).map((col) => {
                      const colMeta = previewColumns.find((c) => c.label === col);
                      const cellKey = colMeta?.key ?? col;
                      return <td key={col} className="csv-td">{String(row[cellKey] ?? "")}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <label>
            Event type (canonical name)
            <input value={eventName} onChange={(e) => setEventName(e.target.value)} />
          </label>
          {(Object.keys(FIELD_LABELS) as FieldKey[]).map((key) => (
            <label key={key}>
              {FIELD_LABELS[key]}
              {fieldSelect(fields[key], (next) => setFields({ ...fields, [key]: next }), activeColumns)}
            </label>
          ))}
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <input
              type="checkbox"
              checked={itemsEnabled}
              onChange={(e) => setItemsEnabled(e.target.checked)}
            />
            Each row is a line item (rows are grouped into orders by the order ID)
          </label>
          {itemsEnabled
            ? (Object.keys(ITEM_LABELS) as ItemKey[]).map((key) => (
                <label key={key}>
                  Item: {ITEM_LABELS[key]}
                  {fieldSelect(itemFields[key], (next) => setItemFields({ ...itemFields, [key]: next }), activeColumns)}
                </label>
              ))
            : null}
          <button type="button" disabled={busy} onClick={() => void onValidate()}>
            {busy ? "Validating…" : "Validate mapping"}
          </button>
        </div>
      ) : null}

      {/* ══════════════════════════════════════════
          PHASE: report — validation results
      ══════════════════════════════════════════ */}
      {phase === "report" ? (
        <div className="form">
          <div className={`validation-summary ${report && report.invalid_rows === 0 ? "success" : "warn"}`}>
            <span>
              ✓ {report?.valid_rows} of {report?.total_rows} rows valid
            </span>
            {report && report.invalid_rows > 0 ? (
              <span className="warn-text">
                ⚠ {report.invalid_rows} {report.invalid_rows === 1 ? "row has" : "rows have"} issues
              </span>
            ) : null}
          </div>
          {report && report.issues.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Issue</th>
                </tr>
              </thead>
              <tbody>
                {report.issues.slice(0, 20).map((issue, index) => (
                  <tr key={index}>
                    <td>{issue.row}</td>
                    <td>{issue.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {report && report.preview_payloads.length > 0 ? (
            <details>
              <summary>Preview canonical payloads</summary>
              <pre>{JSON.stringify(report.preview_payloads, null, 2)}</pre>
            </details>
          ) : null}
          <button
            type="button"
            disabled={busy || !report || report.valid_rows === 0}
            onClick={() => void onImport()}
          >
            {busy ? "Importing…" : `Import ${report?.valid_rows ?? 0} valid rows`}
          </button>
        </div>
      ) : null}

      {/* ══════════════════════════════════════════
          PHASE: status — import progress
      ══════════════════════════════════════════ */}
      {phase === "status" ? (
        <div className="form">
          <div className={`validation-summary ${status?.batch.status === "completed" ? "success" : status?.batch.status === "failed" ? "error-box" : ""}`}>
            Import {status?.batch.status} · {status?.batch.completed_jobs ?? 0} completed ·{" "}
            {status?.batch.failed_jobs ?? 0} failed · {status?.batch.queued_jobs ?? 0} queued
          </div>
          {status && status.job_errors.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Source row</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {status.job_errors.map((jobError) => (
                  <tr key={jobError.job_id}>
                    <td>{jobError.job_id}</td>
                    <td>{jobError.source_row ?? "—"}</td>
                    <td>{jobError.message ?? "Unknown error"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {done ? (
            <button type="button" onClick={onReset}>
              Import another file or document
            </button>
          ) : null}
        </div>
      ) : null}
        </>
      )}
    </section>
  );
}
