"use client";
import { useState } from "react";
import Image from "next/image";
import { Check, Copy, Terminal, ArrowRight } from "lucide-react";

// One-line remote install. Uses the PUBLIC Cognito client (auth-code + PKCE, no
// secret) baked into plugin/.mcp.remote.json — safe to show the world. A new user
// runs this, then `/mcp -> Authenticate` in the browser, and lands as a read-only
// viewer until an operator promotes their account.
const INSTALL_CMD =
  'claude mcp add --transport http --client-id 1phgpdfcrftedtj69hhni18bue ' +
  '--callback-port 8080 sunstead-control ' +
  '"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/' +
  "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A528081867249%3Aruntime%2F" +
  'sunsteadcontrol_sunstead_control-u9zi87DjdX/invocations?qualifier=DEFAULT"';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1800);
        });
      }}
      className="flex items-center gap-1.5 text-xs font-medium text-blue-200 hover:text-white transition-colors flex-shrink-0"
      title="Copy install command"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function PluginHero() {
  return (
    <section className="bg-navy rounded-xl overflow-hidden">
      <div className="grid lg:grid-cols-2">
        {/* Image — drop the exported artifact at frontend/public/plugin-hero.png */}
        <div className="relative min-h-[220px] bg-navy/60 border-b lg:border-b-0 lg:border-r border-white/10">
          <Image
            src="/plugin-hero.png"
            alt="SunsteadHack control plane, driven from Claude Code"
            fill
            priority
            className="object-cover"
          />
        </div>

        {/* Pitch + install */}
        <div className="p-6 lg:p-8 flex flex-col justify-center gap-4">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-blue-300 font-semibold">
              Claude Code plugin
            </span>
            <h2 className="text-xl font-semibold text-white mt-1 leading-snug">
              Drive the control plane from your terminal
            </h2>
            <p className="text-sm text-blue-100 mt-2 leading-relaxed max-w-md">
              Dispatch optimization runs, watch p99 curves, and adjudicate governance
              escalations with slash commands — against this live, role-brokered backend.
              Sign in with your browser; no secret to paste.
            </p>
          </div>

          <div className="bg-black/30 rounded-lg border border-white/10 p-3">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-blue-300 font-semibold">
                <Terminal className="w-3 h-3" /> Install
              </span>
              <CopyButton text={INSTALL_CMD} />
            </div>
            <code className="block text-[11px] leading-relaxed text-blue-50 font-mono break-all whitespace-pre-wrap">
              {INSTALL_CMD}
            </code>
          </div>

          <p className="text-xs text-blue-200/80 leading-relaxed">
            Then run <span className="font-mono text-blue-100">/mcp → Authenticate</span>.
            New users start read-only — an operator promotes you to dispatch &amp; adjudicate.
            <a
              href="https://github.com/PlayerPlanet/SunsteadHack/tree/main/plugin"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-blue-200 hover:text-white underline underline-offset-2 ml-1"
            >
              Commands <ArrowRight className="w-3 h-3" />
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
