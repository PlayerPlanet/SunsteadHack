export { auth as middleware } from "@/auth";

// Require a session for all app pages and data routes. Excluded: the Auth.js endpoints
// (sign-in/callback must be reachable while logged out), the /login page itself, Next
// internals, and public/ static assets (images/fonts/etc.) — the last is important
// because the next/image optimizer fetches a source like /plugin-hero.png server-side
// WITHOUT the session cookie, so gating it would 307 that fetch to /login and the
// optimizer would 400. Unauthenticated app requests redirect to /login (pages.signIn).
export const config = {
  matcher: [
    "/((?!api/auth|login|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|ico|webp|avif|woff2?|ttf|txt)$).*)",
  ],
};
