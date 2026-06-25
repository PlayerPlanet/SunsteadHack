import "server-only";
import { NextResponse } from "next/server";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { auth } from "@/auth";

// Call MCP tools on the deployed AgentCore control-plane runtime, forwarding the caller's
// Cognito access token as the bearer. AgentCore validates it at the edge and (because the
// runtime has requestHeaderAllowlist:["Authorization"]) forwards it to the server, which
// enforces per-tool scope + SET ROLE. ALL dashboard data — reads AND writes — goes through
// this enforced path; there is NO direct-DB connection from the frontend. A viewer gets
// read scopes; dispatch/adjudicate need operator scope and 403 otherwise; a logged-out
// caller has no bearer and is refused.

const RUNTIME_URL = process.env.AGENT_RUNTIME_URL;

export type ToolResult = { isError?: boolean; text: string };

/** Error carrying the HTTP status a route should return (401 unauth, 403 scope, 502 down). */
export class ControlError extends Error {
  status: number;
  constructor(message: string, status = 502) {
    super(message);
    this.status = status;
  }
}

export async function callControlTool(
  bearer: string,
  name: string,
  args: Record<string, unknown>,
): Promise<ToolResult> {
  if (!RUNTIME_URL) throw new Error("AGENT_RUNTIME_URL is not configured");

  const transport = new StreamableHTTPClientTransport(new URL(RUNTIME_URL), {
    requestInit: { headers: { Authorization: `Bearer ${bearer}` } },
  });
  const client = new Client({ name: "sunstead-dashboard", version: "0.1.0" });
  try {
    await client.connect(transport);
    const res: any = await client.callTool({ name, arguments: args });
    const text = (res?.content ?? [])
      .map((c: any) => (typeof c?.text === "string" ? c.text : ""))
      .join("");
    return { isError: !!res?.isError, text };
  } finally {
    await transport.close().catch(() => {});
  }
}

/** Parse a tool's text payload: JSON when structured, raw string for scalars (run_id…), null for None. */
function parseToolText(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Call a tool and return its parsed result; throws ControlError (403 on scope refusal) on isError. */
export async function callControlJson<T = unknown>(
  bearer: string,
  name: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  const res = await callControlTool(bearer, name, args);
  if (res.isError) {
    const status = /scope|role|denied|permission|forbidden|unauthor/i.test(res.text) ? 403 : 502;
    throw new ControlError(res.text || `${name} failed`, status);
  }
  return parseToolText(res.text) as T;
}

/** The signed-in caller's Cognito access token, or a 401 ControlError. */
export async function requireBearer(): Promise<string> {
  const session = await auth();
  if (!session?.accessToken) throw new ControlError("sign in required", 401);
  return session.accessToken;
}

/**
 * Every experiment across the active tasks, via the edge API (read_curve per task).
 * Used by the stats + boundary aggregations the runtime doesn't expose as a single tool.
 * NOTE: scans active tasks only — experiments for unlisted/retired tasks aren't counted
 * (acceptable for the current demo task set).
 */
export async function allExperiments(bearer: string): Promise<any[]> {
  const tasks = await callControlJson<any[]>(bearer, "list_tasks", {});
  const lists = await Promise.all(
    (tasks ?? []).map((t: any) =>
      callControlJson<any[]>(bearer, "read_curve", { task_id: t.task_id }).catch(() => []),
    ),
  );
  return lists.flat();
}

/** Map a thrown error to the right JSON response (preserves ControlError status). */
export function errToResponse(e: unknown): NextResponse {
  if (e instanceof ControlError) {
    return NextResponse.json({ error: e.message }, { status: e.status });
  }
  const msg = e instanceof Error ? e.message : String(e);
  return NextResponse.json({ error: `control plane unreachable: ${msg}` }, { status: 502 });
}
