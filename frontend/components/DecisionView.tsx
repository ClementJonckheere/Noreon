"use client";

import { useState } from "react";
import { ChatResponse, api } from "@/lib/api";

// Decision Engine — des mêmes données, des décisions selon le rôle.
// Chaque décision est justifiée (Decision Journal), porte un impact estimé et
// une priorité effort/impact (⭐), le bloc « et si je ne fais rien ? » projette
// (prudemment) l'inaction, et le décideur peut qualifier une reco (mémoire
// métier → « déjà appliquée avec succès dans un contexte similaire »).
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

const LEVEL_CLS: Record<string, string> = {
  "Élevé": "bg-emerald-500/15 text-emerald-700",
  "Moyen": "bg-amber-500/15 text-amber-700",
  "Faible": "bg-slate-200 text-slate-600",
};

function Stars({ n }: { n: number }) {
  const full = Math.max(1, Math.min(5, n));
  return (
    <span className="shrink-0 tracking-tight" title={`Priorité effort/impact : ${full}/5`}>
      <span className="text-amber-500">{"★".repeat(full)}</span>
      <span className="text-slate-300">{"★".repeat(5 - full)}</span>
    </span>
  );
}

type Decision = NonNullable<ChatResponse["decisions"]>["decisions"][number];

// Retours possibles d'un décideur (human-in-the-loop).
const FEEDBACK = [
  { status: "retained", label: "Je retiens", cls: "text-sky-700 border-sky-500/30" },
  { status: "implemented", label: "Mise en œuvre", cls: "text-violet-700 border-violet-500/30" },
  { status: "successful", label: "A porté ses fruits", cls: "text-emerald-700 border-emerald-500/30" },
];

function DecisionCard(
  { x, connectionId, subject }: { x: Decision; connectionId?: number; subject?: string },
) {
  const [sent, setSent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function qualify(status: string) {
    if (!connectionId || !subject || busy) return;
    setBusy(true);
    try {
      await api.decisionFeedback(connectionId, {
        subject, role: x.role, recommendation: x.recommendation, status,
      });
      setSent(status);
    } catch {
      /* silencieux : la qualification est un bonus, pas un blocage */
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-noreon-border bg-white/60 p-2.5 text-xs space-y-1">
      <div className="font-medium flex items-center gap-1.5">
        <span>{ROLE_ICON[x.role] || "•"}</span>
        <span className="flex-1">{x.role}</span>
        <Stars n={x.stars} />
      </div>

      {/* Mémoire métier : recommandation déjà retenue / éprouvée ailleurs. */}
      {x.history && (
        <div className="text-[11px] text-emerald-700 bg-emerald-500/10 rounded px-1.5 py-0.5">
          ↻ {x.history}
        </div>
      )}

      <div className="text-slate-700">{x.priority}</div>
      <div className="text-emerald-700">→ {x.recommendation}</div>

      {/* Matrice effort / impact : le décideur arbitre selon le coût/bénéfice. */}
      <div className="flex flex-wrap items-center gap-1 pt-0.5">
        <span className={`badge ${LEVEL_CLS[x.impact_level] || LEVEL_CLS["Moyen"]}`}>
          Impact {x.impact_level}
        </span>
        <span className="badge bg-slate-100 text-slate-600">Effort {x.effort}</span>
        {x.impact && (
          <span className="badge bg-emerald-500/15 text-emerald-700">{x.impact}</span>
        )}
      </div>

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

      {/* Boucle d'amélioration : le décideur qualifie la reco. */}
      {connectionId && subject && (
        sent ? (
          <div className="text-[11px] text-emerald-700">✓ Enregistré — merci, cela nourrit les prochaines analyses.</div>
        ) : (
          <div className="flex flex-wrap gap-1 pt-0.5">
            {FEEDBACK.map((f) => (
              <button
                key={f.status}
                onClick={() => qualify(f.status)}
                disabled={busy}
                className={`text-[11px] rounded border px-1.5 py-0.5 hover:bg-slate-50 disabled:opacity-50 ${f.cls}`}
              >
                {f.label}
              </button>
            ))}
          </div>
        )
      )}
    </div>
  );
}

export default function DecisionView(
  { d, connectionId, subject }:
  { d: NonNullable<ChatResponse["decisions"]>; connectionId?: number; subject?: string },
) {
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
          <DecisionCard key={i} x={x} connectionId={connectionId} subject={subject} />
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
        Priorité par ⭐ = rapport effort/impact. Les données sont identiques ; les priorités changent selon le métier.
      </div>
    </div>
  );
}
