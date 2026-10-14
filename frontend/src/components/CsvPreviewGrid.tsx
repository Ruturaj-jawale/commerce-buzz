import { useState, useRef, useCallback } from "react";

export type ColType = "text" | "number" | "date" | "boolean";

export interface ColumnMeta {
  key: string;
  label: string;
  type: ColType;
}

export interface GridRow {
  [col: string]: string;
}

interface CsvPreviewGridProps {
  columns: ColumnMeta[];
  rows: GridRow[];
  onColumnsChange: (cols: ColumnMeta[]) => void;
  onRowsChange: (rows: GridRow[]) => void;
}

const TYPE_ICONS: Record<ColType, string> = {
  text: "Aa",
  number: "#",
  date: "📅",
  boolean: "☑",
};

const TYPE_OPTIONS: { value: ColType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "boolean", label: "Boolean" },
];

function coerce(value: string, type: ColType): string {
  if (!value.trim()) return value;
  switch (type) {
    case "number": {
      const n = Number(value.replace(/[,$\s]/g, ""));
      return isNaN(n) ? value : String(n);
    }
    case "date": {
      const d = new Date(value);
      if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
      return value;
    }
    case "boolean": {
      const lower = value.trim().toLowerCase();
      if (["true", "yes", "1", "y"].includes(lower)) return "true";
      if (["false", "no", "0", "n"].includes(lower)) return "false";
      return value;
    }
    default:
      return value;
  }
}

export function CsvPreviewGrid({ columns, rows, onColumnsChange, onRowsChange }: CsvPreviewGridProps) {
  const [editingCell, setEditingCell] = useState<{ row: number; col: string } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [selectedCol, setSelectedCol] = useState<string | null>(null);
  const [typeMenuCol, setTypeMenuCol] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ── Column type change ───────────────────────────────────────────────────
  const changeType = useCallback(
    (colKey: string, newType: ColType) => {
      onColumnsChange(columns.map((c) => (c.key === colKey ? { ...c, type: newType } : c)));
      onRowsChange(rows.map((row) => ({ ...row, [colKey]: coerce(row[colKey] ?? "", newType) })));
      setTypeMenuCol(null);
    },
    [columns, rows, onColumnsChange, onRowsChange],
  );

  // ── Column rename ────────────────────────────────────────────────────────
  const commitRename = useCallback(() => {
    if (!renaming) return;
    const newLabel = renameValue.trim() || renaming;
    onColumnsChange(columns.map((c) => (c.key === renaming ? { ...c, label: newLabel } : c)));
    setRenaming(null);
  }, [renaming, renameValue, columns, onColumnsChange]);

  // ── Cell edit ────────────────────────────────────────────────────────────
  const startEdit = (rowIdx: number, colKey: string, current: string) => {
    setEditingCell({ row: rowIdx, col: colKey });
    setEditValue(current);
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const commitEdit = useCallback(() => {
    if (!editingCell) return;
    const col = columns.find((c) => c.key === editingCell.col);
    const coerced = col ? coerce(editValue, col.type) : editValue;
    const updated = rows.map((row, i) =>
      i === editingCell.row ? { ...row, [editingCell.col]: coerced } : row,
    );
    onRowsChange(updated);
    setEditingCell(null);
  }, [editingCell, editValue, rows, columns, onRowsChange]);

  // ── Toolbar operations ───────────────────────────────────────────────────
  const fillDown = () => {
    if (!selectedCol) return;
    const firstValue = rows[0]?.[selectedCol] ?? "";
    onRowsChange(rows.map((row) => ({ ...row, [selectedCol]: row[selectedCol] || firstValue })));
  };

  const clearColumn = () => {
    if (!selectedCol) return;
    onRowsChange(rows.map((row) => ({ ...row, [selectedCol]: "" })));
  };

  const deleteColumn = () => {
    if (!selectedCol) return;
    onColumnsChange(columns.filter((c) => c.key !== selectedCol));
    onRowsChange(rows.map((row) => { const r = { ...row }; delete r[selectedCol]; return r; }));
    setSelectedCol(null);
  };

  const trimColumn = () => {
    if (!selectedCol) return;
    onRowsChange(rows.map((row) => ({ ...row, [selectedCol]: (row[selectedCol] ?? "").trim() })));
  };

  const uppercaseColumn = () => {
    if (!selectedCol) return;
    onRowsChange(rows.map((row) => ({ ...row, [selectedCol]: (row[selectedCol] ?? "").toUpperCase() })));
  };

  const lowercaseColumn = () => {
    if (!selectedCol) return;
    onRowsChange(rows.map((row) => ({ ...row, [selectedCol]: (row[selectedCol] ?? "").toLowerCase() })));
  };

  return (
    <div className="csv-preview-wrap">
      {/* ── Toolbar ── */}
      <div className="csv-toolbar">
        <span className="csv-toolbar-label">
          {selectedCol
            ? <>Column: <strong>{columns.find((c) => c.key === selectedCol)?.label ?? selectedCol}</strong></>
            : <span className="muted">Select a column header to use tools</span>}
        </span>
        <div className="csv-toolbar-actions">
          <button type="button" className="tool-btn" disabled={!selectedCol} onClick={fillDown} title="Fill empty cells with the first non-empty value">Fill down</button>
          <button type="button" className="tool-btn" disabled={!selectedCol} onClick={trimColumn} title="Trim whitespace from all cells">Trim</button>
          <button type="button" className="tool-btn" disabled={!selectedCol} onClick={uppercaseColumn} title="UPPERCASE all cells">ABC↑</button>
          <button type="button" className="tool-btn" disabled={!selectedCol} onClick={lowercaseColumn} title="lowercase all cells">abc↓</button>
          <button type="button" className="tool-btn" disabled={!selectedCol} onClick={clearColumn} title="Clear all values in column">Clear</button>
          <button type="button" className="tool-btn danger" disabled={!selectedCol} onClick={deleteColumn} title="Remove this column">✕ Delete col</button>
        </div>
      </div>

      {/* ── Grid ── */}
      <div className="csv-grid-scroll">
        <table className="csv-grid">
          <thead>
            <tr>
              <th className="csv-rn">#</th>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`csv-th${selectedCol === col.key ? " csv-col-selected" : ""}`}
                  onClick={() => setSelectedCol(selectedCol === col.key ? null : col.key)}
                >
                  {/* Type badge / dropdown */}
                  <div className="csv-th-inner">
                    <div className="csv-type-wrap">
                      <button
                        type="button"
                        className="csv-type-btn"
                        title={`Type: ${col.type}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setTypeMenuCol(typeMenuCol === col.key ? null : col.key);
                        }}
                      >
                        {TYPE_ICONS[col.type]}
                      </button>
                      {typeMenuCol === col.key && (
                        <div className="csv-type-menu">
                          {TYPE_OPTIONS.map((opt) => (
                            <button
                              key={opt.value}
                              type="button"
                              className={`csv-type-option${col.type === opt.value ? " active" : ""}`}
                              onClick={(e) => { e.stopPropagation(); changeType(col.key, opt.value); }}
                            >
                              {TYPE_ICONS[opt.value]} {opt.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Column label / rename */}
                    {renaming === col.key ? (
                      <input
                        className="csv-rename-input"
                        value={renameValue}
                        autoFocus
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={(e) => { if (e.key === "Enter") commitRename(); if (e.key === "Escape") setRenaming(null); }}
                        onClick={(e) => e.stopPropagation()}
                      />
                    ) : (
                      <span
                        className="csv-col-label"
                        title="Double-click to rename"
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          setRenaming(col.key);
                          setRenameValue(col.label);
                        }}
                      >
                        {col.label}
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={rowIdx} className={rowIdx % 2 === 0 ? "" : "csv-row-alt"}>
                <td className="csv-rn">{rowIdx + 1}</td>
                {columns.map((col) => {
                  const isEditing = editingCell?.row === rowIdx && editingCell?.col === col.key;
                  const cellValue = String(row[col.key] ?? "");
                  return (
                    <td
                      key={col.key}
                      className={`csv-td${selectedCol === col.key ? " csv-col-selected" : ""}${isEditing ? " csv-editing" : ""}`}
                      onDoubleClick={() => startEdit(rowIdx, col.key, cellValue)}
                    >
                      {isEditing ? (
                        <input
                          ref={inputRef}
                          className="csv-cell-input"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={commitEdit}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") commitEdit();
                            if (e.key === "Escape") setEditingCell(null);
                          }}
                        />
                      ) : (
                        <span className={!cellValue ? "csv-empty" : ""}>{cellValue || "—"}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="csv-hint muted">Double-click any cell to edit · Double-click a header to rename · Click type badge to change data type</p>
    </div>
  );
}
