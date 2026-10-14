import { query } from "../../../database/src/client.js";
import { McpCoreError } from "../../../mcp-core/src/protocol/errors.js";

const identifier = /^[A-Za-z_][A-Za-z0-9_]*$/;
const quoteIdentifier = (value: string) => {
  if (!identifier.test(value)) throw new McpCoreError("INVALID_INPUT", "Schema and table names must be valid PostgreSQL identifiers.");
  return `"${value}"`;
};

export class PostgresConnector {
  async listTables(schema = "public") {
    const result = await query<{ table_name: string }>(
      `SELECT table_name FROM information_schema.tables WHERE table_schema = $1 AND table_type = 'BASE TABLE' ORDER BY table_name`,
      [schema],
    );
    return result.rows.map(({ table_name }) => table_name);
  }

  async getTableSchema(schema: string, table: string) {
    const result = await query<{ column_name: string; data_type: string; is_nullable: string; column_default: string | null }>(
      `SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = $1 AND table_name = $2 ORDER BY ordinal_position`,
      [schema, table],
    );
    return result.rows;
  }

  async runReadOnlyQuery(sql: string) {
    const normalized = sql.trim();
    if (!/^(select|with|explain)\b/i.test(normalized) || /;\s*\S/.test(normalized) || /\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|do)\b/i.test(normalized)) {
      throw new McpCoreError("UNSAFE_QUERY", "Only one read-only SELECT, WITH, or EXPLAIN query is allowed.");
    }
    try {
      const statement = normalized.replace(/;\s*$/, "");
      const limitedStatement = /^explain\b/i.test(statement)
        ? statement
        : `SELECT * FROM (${statement}) AS mcp_result LIMIT 1000`;
      const result = await query(limitedStatement);
      return result.rows;
    } catch (error) {
      throw new McpCoreError("DATABASE_ERROR", "PostgreSQL query failed.", error instanceof Error ? error.message : error);
    }
  }
}
