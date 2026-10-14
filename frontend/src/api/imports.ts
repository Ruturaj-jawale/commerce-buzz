import { getJson, postJson, putJson, uploadFile } from "./client";

export type MappingEntry = { column?: string; const?: unknown };

export type ImportMapping = {
  event_name?: MappingEntry;
  order_id?: MappingEntry;
  revenue?: MappingEntry;
  currency?: MappingEntry;
  customer_id?: MappingEntry;
  occurred_at?: MappingEntry;
  items?: {
    product_id?: MappingEntry;
    name?: MappingEntry;
    price?: MappingEntry;
    quantity?: MappingEntry;
  };
};

export type ImportBatchRead = {
  id: number;
  storefront_id: number;
  filename: string;
  file_kind: string;
  status: "uploaded" | "validated" | "importing" | "completed" | "failed";
  columns: string[];
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  queued_jobs: number;
  processing_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  mapping: ImportMapping | null;
  created_at: string;
};

export type ImportCreated = {
  batch: ImportBatchRead;
  sample_rows: Array<Record<string, unknown>>;
  suggested_mapping: ImportMapping;
};

export type ValidationIssue = { row: number; message: string };

export type ValidationReport = {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  issues: ValidationIssue[];
  preview_payloads: Array<{ event_name: string; payload: Record<string, unknown> }>;
};

export type ImportJobError = { job_id: number; source_row: number | null; message: string | null };

export type ImportStatusRead = {
  batch: ImportBatchRead;
  issues: ValidationIssue[];
  job_errors: ImportJobError[];
};

export function uploadImportFile(
  file: File,
  options: { storefrontId?: number; sourceName?: string; sourceLabel?: string } = {},
): Promise<ImportCreated> {
  if (options.storefrontId) return uploadFile<ImportCreated>(`/api/imports/sources/${options.storefrontId}`, file);
  return uploadFile<ImportCreated>("/api/imports/file", file, {
    source_name: options.sourceName?.trim() || "File import",
    source_label: options.sourceLabel?.trim() || "file-import",
  });
}

export function fetchImport(batchId: number): Promise<ImportStatusRead> {
  return getJson<ImportStatusRead>(`/api/imports/${batchId}`);
}

export function setImportMapping(batchId: number, mapping: ImportMapping): Promise<ValidationReport> {
  return putJson<ValidationReport>(`/api/imports/${batchId}/mapping`, { mapping });
}

export function startImport(batchId: number): Promise<ImportBatchRead> {
  return postJson<ImportBatchRead>(`/api/imports/${batchId}/import`, {});
}
