"use client";
import { Bell } from "lucide-react";

export default function TopBar({ title }: { title: string }) {
  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0">
      <h1 className="text-base font-semibold text-gray-900">{title}</h1>
      <div className="flex items-center gap-3">
        <button className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors">
          <Bell className="w-4 h-4 text-gray-500" />
        </button>
        <div className="flex items-center gap-2 pl-3 border-l border-gray-200">
          <div className="w-7 h-7 rounded-full bg-navy flex items-center justify-center text-white text-xs font-semibold">
            M
          </div>
          <span className="text-sm text-gray-700">mikael.h.myllymaki@gmail.com</span>
        </div>
      </div>
    </header>
  );
}
