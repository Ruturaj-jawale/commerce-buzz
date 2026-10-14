import { Pool, type QueryResultRow } from "pg";

let pool: Pool | undefined;

export function getDatabasePool(): Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;
    if (!connectionString) throw new Error("DATABASE_URL must be configured.");
    pool = new Pool({ connectionString });
  }
  return pool;
}

export async function query<T extends QueryResultRow = QueryResultRow>(text: string, values: unknown[] = []) {
  return getDatabasePool().query<T>(text, values);
}

export async function closeDatabase(): Promise<void> {
  await pool?.end();
  pool = undefined;
}
