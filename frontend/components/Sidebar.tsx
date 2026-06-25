"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, TrendingDown, AlertTriangle, BarChart2, FileText, Settings, Upload } from "lucide-react";

const sections = [
  {
    label: "Data",
    items: [
      { href: "/ingest", label: "Ingest dataset", icon: Upload },
    ],
  },
  {
    label: "Agent Loop",
    items: [
      { href: "/runs", label: "Runs", icon: Zap },
      { href: "/boundary", label: "Boundary", icon: BarChart2 },
    ],
  },
  {
    label: "Governance",
    items: [
      { href: "/escalations", label: "Escalations", icon: AlertTriangle },
    ],
  },
];

export default function Sidebar({ project = "My Project" }: { project?: string }) {
  const path = usePathname();

  return (
    <aside className="w-60 min-h-screen bg-sidebar border-r border-gray-200 flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-navy font-bold text-lg tracking-tight">✕ Sunstead</span>
        </div>
      </div>

      {/* Project selector */}
      <div className="px-4 py-3 border-b border-gray-100">
        <button className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-sm text-left hover:bg-gray-100 transition-colors">
          <div>
            <p className="text-xs text-gray-500 font-medium">Agent Project</p>
            <p className="text-gray-900 font-medium">{project}</p>
          </div>
          <span className="text-gray-400 text-xs">▾</span>
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-5">
        {sections.map((section) => (
          <div key={section.label}>
            <p className="px-2 mb-1 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map(({ href, label, icon: Icon }) => {
                const active = path === href;
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                      active
                        ? "bg-sidebar-active text-navy font-medium"
                        : "text-gray-600 hover:bg-sidebar-hover hover:text-gray-900"
                    }`}
                  >
                    <Icon className={`w-4 h-4 flex-shrink-0 ${active ? "text-navy" : "text-gray-400"}`} />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-3 pb-4 space-y-0.5">
        <Link href="/" className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
          path === "/" ? "bg-sidebar-active text-navy font-medium" : "text-gray-600 hover:bg-sidebar-hover"
        }`}>
          <TrendingDown className="w-4 h-4 text-gray-400" />
          Dashboard
        </Link>
        <a href="https://github.com/PlayerPlanet/SunsteadHack" target="_blank" rel="noreferrer"
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-sidebar-hover transition-colors">
          <FileText className="w-4 h-4 text-gray-400" />
          Docs
        </a>
      </div>
    </aside>
  );
}
