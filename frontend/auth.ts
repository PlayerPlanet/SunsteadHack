import NextAuth from "next-auth";
import Cognito from "next-auth/providers/cognito";

// Decode a JWT payload WITHOUT verifying (the IdP we just authenticated with issued it).
// We read cognito:groups from the ACCESS token so the BFF's role gating uses the SAME
// source the control-plane runtime does (cleanroom.control.server.auth).
function groupsFromAccessToken(accessToken?: string): string[] {
  if (!accessToken) return [];
  try {
    const payload = accessToken.split(".")[1];
    const json = Buffer.from(payload.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");
    const claims = JSON.parse(json);
    const g = claims["cognito:groups"];
    return Array.isArray(g) ? g : [];
  } catch {
    return [];
  }
}

// Cognito's OAuth token endpoint (Hosted-UI domain), discovered once from the issuer's
// OIDC document. This is the SAME endpoint Auth.js used for the initial code exchange,
// so it's the right one for refresh_token grants too.
let _tokenEndpoint: string | undefined;
async function cognitoTokenEndpoint(): Promise<string> {
  if (_tokenEndpoint) return _tokenEndpoint;
  const issuer = (process.env.COGNITO_ISSUER ?? "").replace(/\/$/, "");
  const res = await fetch(`${issuer}/.well-known/openid-configuration`);
  if (!res.ok) throw new Error(`OIDC discovery failed: ${res.status}`);
  _tokenEndpoint = (await res.json()).token_endpoint as string;
  return _tokenEndpoint;
}

// Exchange the stored refresh token for a fresh ACCESS token. Cognito access tokens live
// ~60 min but the Auth.js session lives far longer — without this the BFF forwards an
// expired bearer and AgentCore answers -32001 "Token has expired" on every data route.
async function refreshAccessToken(token: any) {
  try {
    if (!token.refreshToken) throw new Error("no refresh token");
    const clientId = process.env.COGNITO_CLIENT_ID ?? "";
    const clientSecret = process.env.COGNITO_CLIENT_SECRET ?? "";
    const basic = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");
    const res = await fetch(await cognitoTokenEndpoint(), {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        // The dashboard client has a secret, so Cognito requires Basic client auth.
        Authorization: `Basic ${basic}`,
      },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: clientId,
        refresh_token: token.refreshToken,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? `refresh failed: ${res.status}`);
    const accessToken = data.access_token as string;
    return {
      ...token,
      accessToken,
      expiresAt: Date.now() + (data.expires_in ?? 3600) * 1000,
      groups: groupsFromAccessToken(accessToken),
      // Cognito does NOT rotate the refresh token on this grant — keep the existing one.
      refreshToken: data.refresh_token ?? token.refreshToken,
      error: undefined,
    };
  } catch {
    // Surface to the session so the UI can force a fresh sign-in.
    return { ...token, error: "RefreshTokenError" };
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Cognito({
      clientId: process.env.COGNITO_CLIENT_ID,
      clientSecret: process.env.COGNITO_CLIENT_SECRET,
      issuer: process.env.COGNITO_ISSUER,
      // default scope "openid profile email" matches the dashboard app client
    }),
  ],
  callbacks: {
    // Require a signed-in user for everything the middleware matches.
    authorized({ auth }) {
      return !!auth?.user;
    },
    async jwt({ token, account }) {
      // Initial sign-in: persist the ACCESS token (carries cognito:groups — what the
      // control plane reads), the REFRESH token, and an absolute expiry in ms. The id
      // token is not used by the runtime. account.expires_at is absolute UNIX seconds.
      if (account?.access_token) {
        return {
          ...token,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          expiresAt: account.expires_at ? account.expires_at * 1000 : Date.now() + 3600_000,
          groups: groupsFromAccessToken(account.access_token),
        };
      }
      // Still valid (60s safety margin)? Hand it back unchanged.
      if (token.expiresAt && Date.now() < (token.expiresAt as number) - 60_000) {
        return token;
      }
      // Expired (or about to) → rotate via the refresh token.
      return await refreshAccessToken(token);
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.groups = token.groups ?? [];
      session.error = token.error;
      return session;
    },
  },
  pages: { signIn: "/login" },
});
