// Mirror of cleanroom.control.server.auth.DEFAULT_GROUP_ROLE_MAP / _ROLE_SCOPES.
// The dashboard derives the SAME role from the user's Cognito groups that the control
// plane will, so the UI shows exactly the actions the runtime would actually permit.
// The runtime + Postgres SET ROLE remain the source of truth; this is just UX gating.

export type Role = "sunstead_operator" | "sunstead_proposer" | "sunstead_readonly";

const GROUP_ROLE: Record<string, Role> = {
  "sunstead-operators": "sunstead_operator",
  "sunstead-proposers": "sunstead_proposer",
  "sunstead-viewers": "sunstead_readonly",
};

const RANK: Record<Role, number> = {
  sunstead_readonly: 0,
  sunstead_proposer: 1,
  sunstead_operator: 2,
};

/** Highest-privilege role among the user's mapped groups; default = viewer. */
export function roleFromGroups(groups?: string[] | null): Role {
  const mapped = (groups ?? []).map((g) => GROUP_ROLE[g]).filter(Boolean) as Role[];
  if (mapped.length === 0) return "sunstead_readonly";
  return mapped.reduce((a, b) => (RANK[b] > RANK[a] ? b : a));
}

export const canAdjudicate = (role: Role) => role === "sunstead_operator";
export const canDispatch = (role: Role) => role === "sunstead_operator";
export const canRegisterTask = (role: Role) =>
  role === "sunstead_operator" || role === "sunstead_proposer";

export function roleLabel(role: Role): string {
  return { sunstead_operator: "Operator", sunstead_proposer: "Proposer", sunstead_readonly: "Viewer" }[role];
}
