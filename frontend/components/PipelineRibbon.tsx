"use client";

// L'identité de Noreon — les cinq temps de l'analyse autonome. Ce n'est pas un
// simple générateur de SQL : c'est un pipeline qui comprend, relie et raisonne.
//
//   Discover → Understand → Connect → Reason → Reveal
//
const PHASES = [
  { key: "discover", verb: "Discover", role: "Scanner", desc: "cartographie tables, colonnes et clés" },
  { key: "understand", verb: "Understand", role: "Profiler", desc: "types réels, PII, qualité des données" },
  { key: "connect", verb: "Connect", role: "Knowledge Graph", desc: "relie les entités métier" },
  { key: "reason", verb: "Reason", role: "Planner", desc: "planifie, enchaîne, synthétise" },
  { key: "reveal", verb: "Reveal", role: "Insights", desc: "remonte anomalies et opportunités" },
] as const;

export default function PipelineRibbon({ compact = false }: { compact?: boolean }) {
  return (
    <div className="card p-4">
      {!compact && (
        <div className="text-body text-ink-2 mb-3">
          <span className="text-ink font-medium">Le pipeline Noreon</span> — comprendre,
          relier, raisonner. Pas seulement générer du SQL.
        </div>
      )}
      <div className="flex items-stretch gap-1.5 overflow-x-auto">
        {PHASES.map((p, i) => (
          <div key={p.key} className="flex items-stretch gap-1.5">
            {i > 0 && <div className="self-center text-line-strong">→</div>}
            <div className="min-w-[8.5rem] flex-1 rounded-card border border-line-subtle bg-paper-2 p-2.5">
              <div className="text-subhead text-ink">{p.verb}</div>
              <div className="text-label uppercase text-reason mt-0.5">{p.role}</div>
              {!compact && (
                <div className="text-small text-ink-3 mt-1 leading-snug">{p.desc}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
