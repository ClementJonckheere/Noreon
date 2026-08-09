"use client";

import { ChatResponse } from "@/lib/api";

// Rendu du raisonnement de l'agent : plan → étapes (sous-questions + constats) →
// synthèse. Violet : c'est la machine qui interprète. Chaque étape est justifiée
// et porte son SQL (transparence « preuve »).
export default function InvestigationView({
  inv,
}: {
  inv: NonNullable<ChatResponse["investigation"]>;
}) {
  return (
    <div className="card p-4 space-y-4 border-l-[3px] border-l-reason">
      <div className="flex items-center gap-2">
        <span className="tag tag-reason">Raisonnement</span>
        <span className="text-body text-ink-2">
          {inv.steps.length} étape(s) sur <span className="mono text-ink">{inv.subject}</span>
        </span>
      </div>

      {/* Plan annoncé */}
      {inv.plan.length > 0 && (
        <div className="space-y-1">
          <div className="text-label uppercase text-ink-3">Plan d'investigation</div>
          <ol className="text-body space-y-1">
            {inv.plan.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-reason font-medium mono">{i + 1}.</span>
                <span className="text-ink-2">
                  <span className="font-medium text-ink">{p.title}</span> — {p.rationale}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Étapes exécutées */}
      <div className="space-y-2">
        <div className="text-label uppercase text-ink-3">Sous-questions & constats</div>
        {inv.steps.map((s, i) => (
          <div key={i} className="bg-paper-2 rounded-card border border-line-subtle p-2.5 space-y-1">
            <div className="text-body font-medium text-ink">
              {i + 1}. {s.question}
            </div>
            <div className="text-body text-ink-2">{s.finding}</div>
            <details className="text-small text-ink-3">
              <summary className="cursor-pointer hover:text-ink">Pourquoi & SQL</summary>
              <div className="mt-1 text-ink-2">{s.rationale}</div>
              <pre className="mt-1 mono bg-raised border border-line-subtle rounded p-2 overflow-x-auto whitespace-pre-wrap text-ink-2">
                {s.sql}
              </pre>
            </details>
          </div>
        ))}
      </div>

      {/* « Le moteur change d'avis » — révision d'hypothèse (raisonnement). */}
      {inv.revisions?.length > 0 && (
        <div className="rounded-card bg-reason-subtle border border-reason/20 p-2.5 space-y-1">
          <div className="text-label uppercase text-reason">J'ai revu mon analyse</div>
          {inv.revisions.map((r, i) => (
            <div key={i} className="text-body text-ink-2">{r}</div>
          ))}
        </div>
      )}

      {/* Journal de raisonnement (experts) — timeline horodatée. */}
      {inv.journal?.length > 0 && (
        <details className="text-small">
          <summary className="cursor-pointer text-ink-3 hover:text-ink">
            Journal de raisonnement ({inv.journal.length})
          </summary>
          <ol className="mt-2 space-y-1 border-l border-line pl-3">
            {inv.journal.map((j, i) => {
              const dot =
                j.status === "accepted" ? "text-reason"
                : j.status === "rejected" ? "text-ink-3"
                : j.phase === "revision" ? "text-warning-hover"
                : "text-line-strong";
              return (
                <li key={i} className="flex gap-2">
                  <span className="meta text-[10px]">{j.t}</span>
                  <span className={dot}>●</span>
                  <span className="text-ink-2">{j.detail}</span>
                </li>
              );
            })}
          </ol>
        </details>
      )}

      {/* Synthèse */}
      <div className="space-y-1">
        <div className="text-label uppercase text-reason">Synthèse</div>
        <div className="text-subhead text-ink">{inv.conclusion}</div>
        {inv.key_drivers.length > 0 && (
          <div className="text-small text-ink-3">
            Facteurs classés : {inv.key_drivers.join(" · ")}
          </div>
        )}
      </div>

      {inv.recommendations.length > 0 && (
        <div className="space-y-1">
          <div className="text-label uppercase text-brand-700">Prochaines actions</div>
          <ul className="text-body list-disc pl-4 space-y-1 text-ink-2">
            {inv.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
