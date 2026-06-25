"use client";
import { signIn } from "next-auth/react";
import { ShieldCheck } from "lucide-react";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="w-full max-w-sm bg-card border border-border rounded-xl p-8 text-center">
        <ShieldCheck className="w-8 h-8 text-emerald-400 mx-auto mb-4" />
        <h1 className="text-lg font-semibold text-white">Sunstead Control</h1>
        <p className="text-sm text-neutral-500 mt-2 leading-relaxed">
          Sign in to operate the control plane. New users register here too — you start as a
          read-only viewer until an operator grants you more.
        </p>
        <button
          onClick={() => signIn("cognito", { callbackUrl: "/" })}
          className="mt-6 w-full px-4 py-2.5 text-sm rounded bg-white/10 border border-border text-white hover:bg-white/15 transition-colors"
        >
          Sign in / Register
        </button>
        <p className="text-[11px] text-neutral-600 mt-4">
          Authenticated via Amazon Cognito. Your role is enforced by the control plane, not the browser.
        </p>
      </div>
    </div>
  );
}
