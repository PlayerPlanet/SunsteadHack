import postgres from "postgres";

let sql: ReturnType<typeof postgres> | null = null;

export function getDb() {
  if (!process.env.POSTGRES_URL) return null;
  if (!sql) sql = postgres(process.env.POSTGRES_URL, { ssl: "require", max: 3 });
  return sql;
}
