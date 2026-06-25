# Dashboard auth → control-plane role (handoff for the BFF agent)

> **Status: implemented in `frontend/`.** Auth.js (Cognito) login/registration, session,
> middleware, role gating, and the runtime-routed `adjudicate` are wired (`frontend/auth.ts`,
> `middleware.ts`, `lib/roles.ts`, `lib/control.ts`, `app/login/page.tsx`,
> `app/api/escalations/[id]/adjudicate/route.ts`). To run: `cp .env.local.example .env.local`,
> fill the values, `npm install`, `npm run dev`. The sections below are the design rationale.

This is the contract for the dashboard's auth so that **a user who registers gets a
real, enforced role** on the control plane. It's the human-facing complement to the
machine `client_credentials` path.

## The chain (who enforces what)

```
register / sign in (Cognito Hosted UI)
   └─ user lands in a group: sunstead-operators | sunstead-proposers | (none = viewer)
login via BFF  (Auth.js, authorization_code + PKCE)
   └─ BFF receives an ACCESS TOKEN carrying `cognito:groups`
BFF → AgentCore runtime   (HTTP POST, header: Authorization: Bearer <access_token>)
   └─ AgentCore validates the JWT at the edge, then FORWARDS Authorization
      (requestHeaderAllowlist:["Authorization"] on the runtime)
control plane (cleanroom.control.server.auth)
   └─ maps cognito:groups → db_role → SET ROLE in Postgres  ← the truth boundary
```

Two layers enforce, independently:
- **App scope check** (`auth.TOOL_SCOPES`): the role implies `control:*` scopes, so a
  viewer's token can't call `dispatch_run`.
- **Postgres `SET ROLE`** (the hard backstop): even if the app layer were bypassed, a
  `sunstead_readonly` login physically cannot write a judgment. This holds regardless
  of the token.

> The dashboard app client requests **only** `openid email profile` — **no `control:*`
> scopes**. That's deliberate: the user's *group* drives their role and the role
> *implies* the scopes server-side. Don't add resource-server scopes to this client, or
> you'll pin the user to exactly those scopes and bypass the group→role logic.

## Group → role → capability

| Cognito group        | db_role             | Can do                                            |
|----------------------|---------------------|---------------------------------------------------|
| *(none — default)*   | `sunstead_readonly` | read tasks/runs/curves/boundary/escalations       |
| `sunstead-proposers` | `sunstead_proposer` | + register tasks                                  |
| `sunstead-operators` | `sunstead_operator` | + dispatch/cancel runs, adjudicate escalations    |

New sign-ups are **viewers** until an admin promotes them:
```bash
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL_ID" \
  --username <user> --group-name sunstead-operators --region "$REGION"
```

## Values you get from `scripts/setup_cognito_dashboard.sh`

| Env var (BFF)              | Value                                                                 |
|----------------------------|-----------------------------------------------------------------------|
| `COGNITO_ISSUER`           | `https://cognito-idp.<region>.amazonaws.com/<POOL_ID>`                |
| `COGNITO_CLIENT_ID`        | the `sunstead-dashboard` client id                                    |
| `COGNITO_CLIENT_SECRET`    | contents of the gitignored `dashboard_client.secret` (never commit)   |
| `AGENT_RUNTIME_URL`        | the AgentCore invocation URL (see `plugin/.mcp.remote.json`)          |
| `AUTH_SECRET`              | a random 32-byte string for Auth.js session encryption                |

## Auth.js (NextAuth v5) — Cognito provider

```ts
// auth.ts
import NextAuth from "next-auth"
import Cognito from "next-auth/providers/cognito"

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Cognito({
      issuer: process.env.COGNITO_ISSUER,
      clientId: process.env.COGNITO_CLIENT_ID,
      clientSecret: process.env.COGNITO_CLIENT_SECRET,
      // default scope "openid profile email" matches the app client — do not add control:*
    }),
  ],
  callbacks: {
    // Persist the Cognito ACCESS token (it carries cognito:groups) — this is what the
    // control plane reads. The id token is NOT used by the runtime.
    async jwt({ token, account }) {
      if (account?.access_token) token.accessToken = account.access_token
      if (account?.expires_at) token.expiresAt = account.expires_at
      return token
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string
      return session
    },
  },
})
```

Set the callback URL in Cognito to `<DASHBOARD_URL>/api/auth/callback/cognito` (the
setup script already registers prod + `http://localhost:3000`).

## Calling the control plane from the BFF

Forward the **access token** as the bearer. Run this on the **Node.js runtime**
(`export const runtime = "nodejs"`), not Edge — the MCP streamable-HTTP client and
long-poll timeouts don't belong on Edge.

```ts
// app/api/control/[...]/route.ts  (Node runtime)
import { auth } from "@/auth"

export const runtime = "nodejs"

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.accessToken) return new Response("Unauthorized", { status: 401 })

  const res = await fetch(process.env.AGENT_RUNTIME_URL!, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${session.accessToken}`,
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream", // MCP streamable-HTTP requirement
    },
    body: await req.text(),
  })
  return new Response(res.body, { status: res.status, headers: res.headers })
}
```

If you'd rather speak MCP than proxy raw JSON-RPC, point an MCP client at
`AGENT_RUNTIME_URL` with the same `Authorization` header — see `scratchpad/mcp_test.py`
for the exact handshake, and `plugin/.mcp.remote.json` for the URL shape.

## What happens on each role, concretely

- **Viewer** calls `dispatch_run` → app layer returns `403 insufficient_scope`
  (`control:dispatch` required). Even forced through, Postgres rejects the write as
  `sunstead_readonly`.
- **Operator** calls `dispatch_run` → allowed; the run executes under `sunstead_operator`.
- The bright line is unaffected: no role — not even operator — can touch the frozen
  judge/loss/pore. Auth governs *who operates the plane*, never *what the judge scores*.

## Notes / gotchas

- **Token lifetime**: Cognito access tokens default to 60 min. Auth.js refreshes via the
  refresh token (the client has `ALLOW_REFRESH_TOKEN_AUTH`); add refresh handling in the
  `jwt` callback if sessions outlive the access token.
- **`db_role` claim (optional)**: if you deploy `scripts/cognito_pretoken_lambda.py`
  (Essentials feature plan only), tokens also carry an explicit `db_role` claim, which
  the control plane honors at highest precedence. Without it, `cognito:groups` is used —
  no behavior change for the dashboard.
- The new client id must be added to `agentcore.json` `allowedClients` and the runtime
  redeployed before tokens from this client are accepted at the edge (the setup script
  prints this step).
