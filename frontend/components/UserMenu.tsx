"use client";
import { useSession, signIn, signOut } from "next-auth/react";
import { roleFromGroups, roleLabel } from "@/lib/roles";

export default function UserMenu() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return <span className="text-xs text-neutral-600">…</span>;
  }
  if (!session?.user) {
    return (
      <button
        onClick={() => signIn("cognito")}
        className="px-3 py-1.5 text-xs rounded border border-border text-neutral-300 hover:text-white hover:border-neutral-500 transition-colors"
      >
        Sign in
      </button>
    );
  }

  const role = roleFromGroups(session.groups);
  const label = roleLabel(role);
  const roleColor =
    role === "sunstead_operator"
      ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/10"
      : "text-neutral-400 border-border bg-white/5";

  return (
    <div className="flex items-center gap-3">
      <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border ${roleColor}`}>
        {label}
      </span>
      <span className="text-xs text-neutral-400 max-w-[14rem] truncate">{session.user.email}</span>
      <button
        onClick={() => signOut()}
        className="text-xs text-neutral-500 hover:text-neutral-300 transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
