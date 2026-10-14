import * as z from "zod";
import type { ToolDefinition } from "../../../mcp-core/src/protocol/types.js";
import { PostgresConnector } from "./postgres-connector.js";

const asText = (value: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] });

export function createPostgresTools(connector = new PostgresConnector()): ToolDefinition[] {
  return [
    { name: "list_tables", description: "List base tables in a PostgreSQL schema.", inputSchema: z.object({ schema: z.string().default("public") }), execute: async ({ schema }) => asText(await connector.listTables(schema)) },
    { name: "get_table_schema", description: "Get column metadata for a PostgreSQL table.", inputSchema: z.object({ schema: z.string().default("public"), table: z.string().min(1) }), execute: async ({ schema, table }) => asText(await connector.getTableSchema(schema, table)) },
    { name: "run_query", description: "Run a single read-only PostgreSQL SELECT, WITH, or EXPLAIN query (up to 1,000 rows).", inputSchema: z.object({ sql: z.string().min(1).max(100_000) }), execute: async ({ sql }) => asText(await connector.runReadOnlyQuery(sql)) },
  ];
}
