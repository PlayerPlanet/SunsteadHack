"use client";
import { Bell, LogOut } from "lucide-react";
import { useSession, signIn, signOut } from "next-auth/react";
import { roleFromGroups, roleLabel } from "@/lib/roles";

export default function TopBar({ title }: { title: string }) {
  const { data: session, status } = useSession();
  const role = roleFromGroups(session?.groups);
  const email = session?.user?.email ?? "";
  const initial = (email[0] ?? "?").toUpperCase();
  const roleColor =
    role === "sunstead_operator"
      ? "bg-emerald-100 text-emerald-700 border-emerald-200"
      : "bg-gray-100 text-gray-500 border-gray-200";

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0">
      <h1 className="text-base font-semibold text-gray-900">{title}</h1>
      <div className="flex items-center gap-3">
        <button className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors">
          <Bell className="w-4 h-4 text-gray-500" />
        </button>
        {status === "loading" ? (
          <span className="text-xs text-gray-400 pl-3 border-l border-gray-200">…</span>
        ) : session?.user ? (
          <div className="flex items-center gap-2 pl-3 border-l border-gray-200">
            <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded border font-semibold ${roleColor}`}>
              {roleLabel(role)}
            </span>
            <div className="w-7 h-7 rounded-full bg-navy flex items-center justify-center text-white text-xs font-semibold">
              {initial}
            </div>
            <span className="text-sm text-gray-700 max-w-[16rem] truncate">{email}</span>
            <button
              onClick={() => signOut()}
              title="Sign out"
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => signIn("cognito")}
            className="pl-3 border-l border-gray-200 text-sm text-navy font-medium hover:underline"
          >
            Sign in
          </button>
        )}
      </div>
    </header>
  );
}
