"use client";

import { useState } from "react";
import { ChatResponse, api } from "@/lib/api";

// Decision Engine — des mêmes données, des décisions selon le rôle.
// Panneau violet : ces décisions sont produites par le raisonnement. La couleur
// suit la règle stricte : le bleu dit « vous pouvez agir » (recommandation), le
// vert ne dit JAMAIS une hausse ni un impact favorable — un impact projeté se
// lit en neutre, avec son signe.

// Priorité effort/impact — le remplissage est neutre (magnitude), pas un jugement.
function Stars({ n }: { n: number }) {
  const full = Math.max(1, Math.min(5, n));
  return (
    <span className="shrink-0 tracking-tight meta" title={`Priorité effort/impact : ${full}/5`}>
      <span className="text-ink">{"★".repeat(full)}</span>
      <span className="text-line-strong">{"★".repeat(5 - full)}</span>
    </span>
  );
}

type Decision = NonNullable<ChatResponse["decisions"]>["decisions"][number];

// Retours d'un décideur (human-in-the-loop). Bleu = geste, violet = en cours,
// vert = résultat mesuré (validation externe — le seul emploi légitime du vert).
const FEEDBACK = [
  { status: "retained", label: "Je retiens", cls: "text-brand-700 border-brand-200 hover:bg-brand-50" },
  { status: "implemented", label: "Mise en œuvre", cls: "text-reason border-reason/30 hover:bg-reason-subtle" },
  { status: "successful", label: "A porté ses fruits", cls: "text-success-hover border-success/30 hover:bg-success-subtle" },
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
    <div className="rounded-card border border-line bg-raised p-3 space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-subhead text-ink">{x.role}</span>
        <Stars n={x.stars} />
      </div>

      {/* Mémoire métier : recommandation déjà éprouvée ailleurs — résultat mesuré. */}
      {x.history && (
        <div className="text-small text-success-hover bg-success-subtle rounded-field px-2 py-1">
          {x.history}
        </div>
      )}

      <div className="text-body text-ink-2">{x.priority}</div>
      {/* La recommandation est une action : bleu « vous pouvez agir », jamais vert. */}
      <div className="text-body text-brand-700 font-medium">{x.recommendation}</div>

      {/* Matrice effort / impact — étiquettes neutres (magnitude, pas jugement). */}
      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
        <span className="tag tag-neutral">Impact {x.impact_level}</span>
        <span className="tag tag-neutral">Effort {x.effort}</span>
        {x.impact && <span className="tag tag-neutral"><span className="mono">{x.impact}</span></span>}
      </div>

      {x.impact && (
        <div className="text-small text-ink-3">
          Impact estimé <span className="mono">{x.impact}</span>
          {x.impact_confidence && <> · confiance {x.impact_confidence}</>}{" "}
          · estimation basée sur la structure historique des données.
        </div>
      )}

      {x.justification && (
        <details className="text-small text-ink-3">
          <summary className="cursor-pointer hover:text-ink">Pourquoi cette recommandation ?</summary>
          <div className="mt-1 text-ink-2">{x.justification}</div>
        </details>
      )}

      {connectionId && subject && (
        sent ? (
          <div className="text-small text-success-hover">Enregistré — merci, cela nourrit les prochaines analyses.</div>
        ) : (
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {FEEDBACK.map((f) => (
              <button
                key={f.status}
                onClick={() => qualify(f.status)}
                disabled={busy}
                className={`text-small rounded-field border px-2 py-0.5 transition-colors disabled:opacity-50 ${f.cls}`}
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
    <div className="card p-4 space-y-3 border-l-[3px] border-l-reason">
      <div className="flex items-center gap-2">
        <span className="tag tag-reason">Décisions</span>
        <span className="text-heading text-ink">Selon le rôle</span>
      </div>
      {d.restated && (
        <div className="text-body text-ink-2">
          Objectif compris : <span className="font-medium text-ink">{d.restated}</span>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-2.5">
        {d.decisions.map((x, i) => (
          <DecisionCard key={i} x={x} connectionId={connectionId} subject={subject} />
        ))}
      </div>

      {/* « Et si je ne fais rien ? » — projection prudente, en neutre (pas une
          alarme : l'orange dirait à tort une urgence à traiter). */}
      {d.inaction && (
        <div className="rounded-card border border-line-subtle bg-paper-2 px-3 py-2.5 text-body text-ink-2">
          <span className="font-medium text-ink">Et si je ne fais rien ? </span>
          {d.inaction}
        </div>
      )}

      <div className="text-small text-ink-3">
        Priorité par ★ = rapport effort/impact. Les données sont identiques ; les priorités changent selon le métier.
      </div>
    </div>
  );
}
