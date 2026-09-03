"use client";

import { useState } from "react";
import Link from "next/link";
import { ChatResponse } from "@/lib/api";
import ConfidenceBreakdown, { TechnicalControls } from "@/components/ConfidenceBreakdown";
import EvidenceGraph from "@/components/EvidenceGraph";
import { InvestigationChain } from "@/components/InvestigationView";

// Panneau droit CONTEXTUEL : ce que regarde l'utilisateur — Comprendre, Preuve,
// Source, Limite qualité — et non une seconde navigation de conversations.
type Tab = "comprendre" | "preuve" | "source";

export default function RightPanel({ r, connectionId }: { r: ChatResponse; connectionId?: number }) {
  const [tab, setTab] = useState<Tab>("comprendre");
  const hasProof = !!r.sql || (r.columns?.length ?? 0) > 0;
  const hasSources = (r.sources?.length ?? 0) > 0 || (r.tables_used?.length ?? 0) > 0;

  return (
    <aside className="w-[360px] shrink-0 border-l border-line-subtle bg-bg-primary flex flex-col overflow-hidden">
      <div className="h-[52px] shrink-0 flex items-center gap-1 px-3 border-b border-line-subtle">
        <TabButton active={tab === "comprendre"} onClick={() => setTab("comprendre")}>Comprendre</TabButton>
        {hasProof && <TabButton active={tab === "preuve"} onClick={() => setTab("preuve")}>Preuve</TabButton>}
        {hasSources && <TabButton active={tab === "source"} onClick={() => setTab("source")}>Sources</TabButton>}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 density-dense">
        {tab === "comprendre" && (
          <>
            {r.confidence && <ConfidenceBreakdown c={r.confidence} r={r} connectionId={connectionId} />}
            {r.self_critique?.length > 0 && (
              <div className="state state-limit">
                <div className="state-title">Ce qui pourrait remettre en question cette conclusion</div>
                <ul className="state-body space-y-0.5">
                  {r.self_critique.map((c, i) => <li key={i}>{asSentence(c)}</li>)}
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
            {/* Chaîne établie — le raisonnement pas à pas, déplacé du centre. */}
            {r.investigation?.steps && <InvestigationChain steps={r.investigation.steps} />}

            {/* Lignage : concept métier → traduction physique (ici, la technicité
                est une qualité — nous sommes dans la Preuve). */}
            {r.investigation?.lineage && (
              <div className="space-y-2">
                <div className="text-label uppercase text-ink-tertiary">Concepts → physique</div>
                <LineageCard
                  concept={r.investigation.lineage.measure.concept}
                  definition={r.investigation.lineage.measure.definition_version}
                  physical={
                    r.investigation.lineage.measure.table && r.investigation.lineage.measure.column
                      ? `${r.investigation.lineage.measure.table}.${r.investigation.lineage.measure.column}`
                      : r.investigation.metric_label
                  }
                  aggregation={r.investigation.lineage.measure.aggregation}
                />
                {r.investigation.lineage.dimensions.map((d, i) => (
                  <LineageCard key={i} concept={d.concept} definition={d.definition_version} physical={d.physical ?? d.physical_label} />
                ))}
              </div>
            )}
            {/* Contrôles techniques — distincts des dimensions métier de confiance. */}
            <TechnicalControls c={r.confidence} r={r} />
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
              {(r.sources ?? []).map((s) => {
                const row = (
                  <div className="flex items-center justify-between rounded-field border border-line-subtle px-3 py-2 hover:border-line-strong transition-colors">
                    <span className="mono text-body text-ink-primary">{s.table}</span>
                    <span className="meta">{s.role}{s.quality_pct !== null ? ` · qualité ${s.quality_pct}%` : ""}</span>
                  </div>
                );
                // Drill-down : chaque source mène à sa fiche de confiance (Qualité).
                return connectionId ? (
                  <Link key={s.table} href={`/quality/${connectionId}?table=${encodeURIComponent(s.table)}`}>{row}</Link>
                ) : <div key={s.table}>{row}</div>;
              })}
              {(r.sources?.length ?? 0) === 0 && r.tables_used?.map((t) => (
                <div key={t} className="rounded-field border border-line-subtle px-3 py-2 mono text-body text-ink-primary">{t}</div>
              ))}
            </div>
            <Link href={connectionId ? `/quality/${connectionId}` : "/quality"} className="btn-secondary btn-sm w-full">
              Confiance de la source →
            </Link>
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

// Les fragments d'auto-critique du moteur ne suivent pas tous le même gabarit
// (« suppose que… », « la période récente… ») : on les rend comme des phrases,
// sans préfixe « Cette analyse » qui produisait des phrases cassées.
function asSentence(fragment: string): string {
  const f = (fragment || "").trim();
  const s = /^(suppose|considère|retient|écarte|ignore)\b/i.test(f) ? `Cette analyse ${f}` : f;
  const capped = s.charAt(0).toUpperCase() + s.slice(1);
  return /[.!?]$/.test(capped) ? capped : `${capped}.`;
}

function LineageCard({
  concept, definition, physical, aggregation,
}: {
  concept: string;
  definition: number | null;
  physical: string;
  aggregation?: string | null;
}) {
  return (
    <div className="rounded-card border border-line-subtle px-3 py-2.5 space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-subhead text-ink-primary">{concept}</span>
        <span className="text-label uppercase text-ink-tertiary">
          {definition != null ? `Concept · définition ${definition}` : "Concept · proposé"}
        </span>
      </div>
      <div className="grid grid-cols-[64px_1fr] gap-x-2 gap-y-0.5">
        <span className="text-label uppercase text-ink-tertiary">Physique</span>
        <span className="mono text-small text-ink-secondary">{physical}</span>
        {aggregation && (
          <>
            <span className="text-label uppercase text-ink-tertiary">Agrégation</span>
            <span className="mono text-small text-ink-secondary">{aggregation}</span>
          </>
        )}
      </div>
    </div>
  );
}
