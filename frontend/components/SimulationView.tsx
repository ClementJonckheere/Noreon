"use client";

import { ChatResponse } from "@/lib/api";

// « What if ? » — la simulation. Noreon quitte l'analyse pour la projection,
// avec ses hypothèses affichées (une projection, pas une prédiction).
export default function SimulationView({ s }: { s: NonNullable<ChatResponse["simulation"]> }) {
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  const up = s.projected.delta_pct >= 0;
  return (
    <div className="card p-4 space-y-3 border border-fuchsia-500/30">
      <div className="text-sm font-semibold text-fuchsia-700">
        🔮 Simulation — {s.scenario}
      </div>
      <div className="text-sm">{s.narrative}</div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="rounded-lg bg-slate-50 border border-noreon-border px-3 py-2 text-xs">
          <div className="text-noreon-soft">Aujourd'hui</div>
          <div className="text-base font-semibold mono">{fmt(s.projected.before)}</div>
        </div>
        <span className="text-fuchsia-500 text-lg">→</span>
        <div className="rounded-lg bg-fuchsia-500/5 border border-fuchsia-500/25 px-3 py-2 text-xs">
          <div className="text-noreon-soft">Projeté</div>
          <div className="text-base font-semibold mono">{fmt(s.projected.after)}</div>
        </div>
        <span className={`text-sm font-semibold ${up ? "text-emerald-600" : "text-red-600"}`}>
          {up ? "+" : ""}
          {s.projected.delta_pct}% ({up ? "+" : ""}
          {fmt(s.projected.delta_abs)})
        </span>
      </div>

      {s.breakdown.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-700">Où atterrit le gain</div>
          <ul className="text-xs space-y-0.5">
            {s.breakdown.map((b, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span>
                  {b.segment} <span className="text-noreon-soft">({b.dimension})</span>
                </span>
                <span className="mono">
                  {b.share}% · +{fmt(b.gain)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="text-xs text-noreon-soft">
        <summary className="cursor-pointer">Hypothèses de la projection</summary>
        <ul className="mt-1 list-disc pl-4 space-y-0.5">
          {s.assumptions.map((a, i) => (
            <li key={i}>{a}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
