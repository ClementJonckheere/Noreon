"use client";

import { useState } from "react";
import Link from "next/link";
import { ChatResponse } from "@/lib/api";
import ConfidenceBreakdown from "@/components/ConfidenceBreakdown";
import EvidenceGraph from "@/components/EvidenceGraph";

// Panneau droit CONTEXTUEL : ce que regarde l'utilisateur — Comprendre, Preuve,
// Source, Limite qualité — et non une seconde navigation de conversations.
type Tab = "comprendre" | "preuve" | "source";

export default function RightPanel({ r }: { r: ChatResponse }) {
  const [tab, setTab] = useState<Tab>("comprendre");
  const hasProof = !!r.sql || (r.columns?.length ?? 0) > 0;
  const hasSources = (r.sources?.length ?? 0) > 0 || (r.tables_used?.length ?? 0) > 0;

  return (
    <aside className="w-[360px] shrink-0 border-l border-line-subtle bg-bg-primary flex flex-col overflow-hidden">
      <div className="h-[52px] shrink-0 flex items-center gap-1 px-3 border-b border-line-subtle">
        <TabButton active={tab === "comprendre"} onClick={() => setTab("comprendre")}>Comprendre</TabButton>
        {hasProof && <TabButton active={tab === "preuve"} onClick={() => setTab("preuve")}>Preuve</TabButton>}
        {hasSources && <TabButton active={tab === "source"} onClick={() => setTab("source")}>Source</TabButton>}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 density-dense">
        {tab === "comprendre" && (
          <>
            {r.confidence && <ConfidenceBreakdown c={r.confidence} />}
            {r.self_critique?.length > 0 && (
              <div className="state state-limit">
                <div className="state-title">Ce qui pourrait remettre en question cette conclusion</div>
                <ul className="state-body space-y-0.5">
                  {r.self_critique.map((c, i) => <li key={i}>Cette analyse {c}.</li>)}
                </ul>
              </div>
            )}
            {r.assumptions?.length > 0 && (
              <div>
                <div className="text-label uppercase text-ink-tertiary mb-1.5">Hypothèses retenues</div>
                <ul className="list-disc pl-4 text-body text-ink-secondary space-y-0.5">
                  {r.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              </div>
            )}
            {!r.confidence && !r.self_critique?.length && !r.assumptions?.length && (
              <Empty>La confiance et les hypothèses apparaîtront ici une fois l'analyse aboutie.</Empty>
            )}
          </>
        )}

        {tab === "preuve" && (
          <>
            <EvidenceGraph r={r} />
            {r.sql && (
              <pre className="mono bg-bg-secondary border border-line-subtle rounded-card p-3 overflow-x-auto whitespace-pre-wrap text-small text-ink-secondary">
                {r.sql}
              </pre>
            )}
            <div className="flex flex-wrap gap-4 meta">
              {r.duration_ms != null && <span>{r.duration_ms} ms</span>}
              <span>{r.row_count} ligne(s)</span>
            </div>
          </>
        )}

        {tab === "source" && (
          <>
            <div className="text-label uppercase text-ink-tertiary">Sources utilisées</div>
            <div className="space-y-1.5">
              {(r.sources ?? []).map((s) => (
                <div key={s.table} className="flex items-center justify-between rounded-field border border-line-subtle px-3 py-2">
                  <span className="mono text-body text-ink-primary">{s.table}</span>
                  <span className="meta">{s.role}{s.quality_pct !== null ? ` · ${s.quality_pct}%` : ""}</span>
                </div>
              ))}
              {(r.sources?.length ?? 0) === 0 && r.tables_used?.map((t) => (
                <div key={t} className="rounded-field border border-line-subtle px-3 py-2 mono text-body text-ink-primary">{t}</div>
              ))}
            </div>
            <Link href="/data" className="btn-secondary btn-sm w-full">Détail des sources</Link>
          </>
        )}
      </div>
    </aside>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 h-8 rounded-[6px] text-[12.5px] transition-colors ${
        active ? "bg-brand-100 text-brand-700 font-medium" : "text-ink-secondary hover:text-ink-primary"
      }`}
    >
      {children}
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-body text-ink-tertiary">{children}</p>;
}
