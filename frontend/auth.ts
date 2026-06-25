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
      // Persist the Cognito ACCESS token (carries cognito:groups) — this is what the
      // control plane reads. The id token is not used by the runtime.
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.expiresAt = account.expires_at;
        token.groups = groupsFromAccessToken(account.access_token);
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken;
      session.groups = token.groups ?? [];
      return session;
    },
  },
  pages: { signIn: "/login" },
});
