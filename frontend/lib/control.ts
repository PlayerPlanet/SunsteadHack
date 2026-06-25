import "server-only";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

// Call an MCP tool on the deployed AgentCore control-plane runtime, forwarding the
// caller's Cognito access token as the bearer. AgentCore validates it at the edge and
// (because the runtime has requestHeaderAllowlist:["Authorization"]) forwards it to the
// server, which enforces per-tool scope + SET ROLE. So privileged dashboard actions go
// through the SAME enforced path as the MCP plugin — no direct-DB backdoor.

const RUNTIME_URL = process.env.AGENT_RUNTIME_URL;

export type ToolResult = { isError?: boolean; text: string };

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
