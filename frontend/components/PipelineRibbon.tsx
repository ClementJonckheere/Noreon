"use client";

// L'identité de Noreon — les cinq temps de l'analyse autonome. Ce n'est pas un
// simple générateur de SQL : c'est un pipeline qui comprend, relie et raisonne.
//
//   Discover → Understand → Connect → Reason → Reveal
//
const PHASES = [
  { key: "discover", verb: "Discover", role: "Scanner", desc: "cartographie tables, colonnes et clés", emoji: "🔎" },
  { key: "understand", verb: "Understand", role: "Profiler", desc: "types réels, PII, qualité des données", emoji: "🧠" },
  { key: "connect", verb: "Connect", role: "Knowledge Graph", desc: "relie les entités métier", emoji: "🕸️" },
  { key: "reason", verb: "Reason", role: "Planner", desc: "planifie, enchaîne, synthétise", emoji: "🧩" },
  { key: "reveal", verb: "Reveal", role: "Insights", desc: "remonte anomalies et opportunités", emoji: "✨" },
] as const;

export default function PipelineRibbon({ compact = false }: { compact?: boolean }) {
  return (
    <div className="card p-4">
      {!compact && (
        <div className="text-sm font-medium mb-3">
          Le pipeline Noreon —{" "}
          <span className="text-noreon-soft font-normal">
            comprendre, relier, raisonner. Pas seulement générer du SQL.
          </span>
        </div>
      )}
      <div className="flex items-stretch gap-1.5 overflow-x-auto">
        {PHASES.map((p, i) => (
          <div key={p.key} className="flex items-stretch gap-1.5">
            {i > 0 && <div className="self-center text-noreon-border">→</div>}
            <div className="min-w-[8.5rem] flex-1 rounded-lg border border-noreon-border bg-white/60 p-2.5">
              <div className="flex items-center gap-1.5">
                <span>{p.emoji}</span>
                <span className="text-sm font-semibold">{p.verb}</span>
              </div>
              <div className="text-[11px] text-indigo-700 mt-0.5">{p.role}</div>
              {!compact && (
                <div className="text-[11px] text-noreon-soft mt-0.5 leading-snug">{p.desc}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
