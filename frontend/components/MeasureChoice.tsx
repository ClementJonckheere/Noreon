"use client";

import { ChatResponse } from "@/lib/api";

// Mesures contradictoires — quand plusieurs montants coexistent (amount /
// amount_ttc / net_price), le moteur explique qu'il y a un choix, RECOMMANDE
// (TTC par défaut) et justifie. Il ne fusionne jamais en silence.
const KIND_BADGE: Record<string, string> = {
  TTC: "bg-emerald-500/15 text-emerald-700",
  HT: "bg-amber-500/15 text-amber-700",
};

export default function MeasureChoice({ m }: { m: NonNullable<ChatResponse["measure_options"]> }) {
  return (
    <div className="card p-4 space-y-2 border border-amber-500/25">
      <div className="text-sm font-semibold text-amber-700">
        ⚖️ Mesure retenue : <span className="mono">{m.chosen}</span>
        {m.chosen_kind && (
          <span className={`badge ml-2 ${KIND_BADGE[m.chosen_kind] || ""}`}>{m.chosen_kind}</span>
        )}
      </div>
      <div className="text-xs text-slate-600">{m.reason}</div>
      <div className="flex flex-wrap gap-1.5">
        {m.options.map((o) => (
          <span
            key={o.column}
            className={`text-xs rounded-lg border px-2 py-1 ${
              o.chosen ? "border-amber-500/50 bg-amber-500/10" : "border-noreon-border bg-white/60"
            }`}
            title={o.note}
          >
            <span className="mono">{o.column}</span>
            {o.kind && <span className="text-noreon-soft"> · {o.kind}</span>}
            {o.recommended && <span className="text-emerald-600"> ✓ recommandé</span>}
          </span>
        ))}
      </div>
    </div>
  );
}
