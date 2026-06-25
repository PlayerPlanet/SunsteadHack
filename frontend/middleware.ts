export { auth as middleware } from "@/auth";

// Require a session for all app pages and data routes. Excluded: the Auth.js endpoints
// (sign-in/callback must be reachable while logged out), the /login page itself, and
// Next static assets. Unauthenticated requests are redirected to /login (pages.signIn).
export const config = {
  matcher: ["/((?!api/auth|login|_next/static|_next/image|favicon.ico).*)"],
};
