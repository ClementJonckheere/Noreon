"use client";

import { ChatResponse } from "@/lib/api";

// Decision Engine — des mêmes données, des décisions selon le rôle.
// On passe de l'analyse (« ce qui se passe ») à la décision (« que faire, selon
// qui je suis »).
const ROLE_ICON: Record<string, string> = {
  "Directeur financier": "💰",
  "Responsable CRM": "🤝",
  "Directeur réseau": "🏬",
  "Directeur produit": "📦",
  "Responsable des opérations": "⚙️",
};

export default function DecisionView({ d }: { d: NonNullable<ChatResponse["decisions"]> }) {
  return (
    <div className="card p-4 space-y-3 border border-violet-500/30">
      <div className="flex items-center gap-2 text-sm font-semibold text-violet-700">
        🧭 Décisions selon le rôle
        {d.intent_label && (
          <span className="badge bg-violet-500/10 text-violet-700 font-normal">
            🎯 {d.intent_label}
          </span>
        )}
      </div>
      <div className="grid sm:grid-cols-2 gap-2">
        {d.decisions.map((x, i) => (
          <div key={i} className="rounded-lg border border-noreon-border bg-white/60 p-2.5 text-xs">
            <div className="font-medium flex items-center gap-1.5">
              <span>{ROLE_ICON[x.role] || "•"}</span>
              {x.role}
            </div>
            <div className="mt-1 text-slate-700">{x.priority}</div>
            <div className="mt-1 text-emerald-700">→ {x.recommendation}</div>
          </div>
        ))}
      </div>
      <div className="text-[11px] text-noreon-soft">
        Les données sont identiques ; les priorités changent selon le métier.
      </div>
    </div>
  );
}
