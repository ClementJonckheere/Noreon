"use client";

import { ChatResponse } from "@/lib/api";

// Décomposition de l'indice de confiance : on voit d'un coup d'œil ce qui le
// construit — et ce qui le pénalise.
const COLORS: Record<string, string> = {
  qualité: "bg-emerald-400",
  concepts: "bg-sky-400",
  relations: "bg-indigo-400",
  SQL: "bg-violet-400",
  couverture: "bg-amber-400",
  hypothèses: "bg-rose-400",
};

export default function ConfidenceBreakdown({ c }: { c: NonNullable<ChatResponse["confidence"]> }) {
  const bd = c.breakdown ?? [];
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">Indice de confiance</span>
        <span
          className={
            c.percent >= 80 ? "text-emerald-700" : c.percent >= 60 ? "text-amber-700" : "text-red-600"
          }
        >
          {c.percent}%
        </span>
      </div>

      {bd.length > 0 && (
        <>
          {/* Barre empilée : chaque composante contribue à hauteur de sa part. */}
          <div className="flex h-2.5 rounded-full overflow-hidden bg-slate-200">
            {bd.map((f) => (
              <div
                key={f.factor}
                className={COLORS[f.factor] || "bg-slate-400"}
                style={{ width: `${f.contribution_pct}%` }}
                title={`${f.factor} : ${f.contribution_pct}% (poids ${f.weight_pct}%, sous-score ${f.subscore_pct}%)`}
              />
            ))}
          </div>
          <ul className="text-xs space-y-0.5">
            {bd.map((f) => (
              <li key={f.factor} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  <span className={`inline-block w-2 h-2 rounded-full ${COLORS[f.factor] || "bg-slate-400"}`} />
                  {f.factor}
                </span>
                <span className="text-noreon-soft">
                  <span className="mono">{f.contribution_pct}%</span>
                  <span className="text-slate-400"> / {f.weight_pct}%</span>
                  {f.subscore_pct < 100 && <span className="text-amber-600"> · {f.subscore_pct}%</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {c.factors?.length > 0 && (
        <div className="text-[11px] text-noreon-soft">{c.factors.join(" · ")}</div>
      )}
    </div>
  );
}
