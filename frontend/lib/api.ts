/** Thin proxy to the Sunstead control plane HTTP shim. */
const BASE = (process.env.CONTROL_PLANE_URL ?? "").replace(/\/$/, "");

export function hasControlPlane() {
  return BASE.length > 0;
}

export async function cp<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Control plane ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}
