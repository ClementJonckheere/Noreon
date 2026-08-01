"use client";

import { ChatResponse } from "@/lib/api";

// Decision Engine — des mêmes données, des décisions selon le rôle.
// Chaque décision est justifiée (Decision Journal), porte un impact estimé,
// et le bloc « et si je ne fais rien ? » projette (prudemment) l'inaction.
const ROLE_ICON: Record<string, string> = {
  "Directeur financier": "💰",
  "Responsable CRM": "🤝",
  "Directeur réseau": "🏬",
  "Directeur produit": "📦",
  "Responsable des opérations": "⚙️",
};

const CONF_CLS: Record<string, string> = {
  "Élevée": "text-emerald-700",
  "Moyenne": "text-amber-700",
  "Faible": "text-slate-500",
};

export default function DecisionView({ d }: { d: NonNullable<ChatResponse["decisions"]> }) {
  return (
    <div className="card p-4 space-y-3 border border-violet-500/30">
      <div className="text-sm font-semibold text-violet-700">🧭 Décisions selon le rôle</div>
      {d.restated && (
        <div className="text-xs text-slate-600">
          🎯 Objectif compris : <span className="font-medium">{d.restated}</span>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-2">
        {d.decisions.map((x, i) => (
          <div key={i} className="rounded-lg border border-noreon-border bg-white/60 p-2.5 text-xs space-y-1">
            <div className="font-medium flex items-center gap-1.5">
              <span>{ROLE_ICON[x.role] || "•"}</span>
              <span className="flex-1">{x.role}</span>
              {x.impact && (
                <span className="badge bg-emerald-500/15 text-emerald-700 shrink-0">
                  {x.impact}
                </span>
              )}
            </div>
            <div className="text-slate-700">{x.priority}</div>
            <div className="text-emerald-700">→ {x.recommendation}</div>
            {x.impact && (
              <div className="text-[11px] text-noreon-soft">
                Impact estimé {x.impact}
                {x.impact_confidence && (
                  <> · confiance <span className={CONF_CLS[x.impact_confidence] || ""}>{x.impact_confidence}</span></>
                )}{" "}· estimation basée sur la structure historique des données.
              </div>
            )}
            {x.justification && (
              <details className="text-[11px] text-noreon-soft">
                <summary className="cursor-pointer">Pourquoi cette recommandation ?</summary>
                <div className="mt-0.5 text-slate-600">{x.justification}</div>
              </details>
            )}
          </div>
        ))}
      </div>

      {/* « Et si je ne fais rien ? » — projection prudente, jamais une prédiction. */}
      {d.inaction && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/25 p-2.5 text-xs text-amber-800">
          <span className="font-medium">Et si je ne fais rien ? </span>
          {d.inaction}
        </div>
      )}

      <div className="text-[11px] text-noreon-soft">
        Les données sont identiques ; les priorités changent selon le métier.
      </div>
    </div>
  );
}
