"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import UserMenu from "@/components/UserMenu";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/boundary", label: "Boundary" },
  { href: "/runs", label: "Runs" },
  { href: "/escalations", label: "Escalations" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="border-b border-border px-6 py-4 flex items-center gap-8">
      <span className="text-white font-semibold tracking-tight text-sm">Sunstead</span>
      <div className="flex gap-1">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`px-3 py-1.5 rounded text-sm transition-colors ${
              path === l.href
                ? "bg-white/10 text-white"
                : "text-neutral-400 hover:text-neutral-200 hover:bg-white/5"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>
      <div className="ml-auto flex items-center gap-4">
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-neutral-500">Live</span>
        </span>
        <UserMenu />
      </div>
    </nav>
  );
}
