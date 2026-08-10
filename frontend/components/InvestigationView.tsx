"use client";

import { ChatResponse } from "@/lib/api";

// Rendu du raisonnement de l'agent (écrans 03–05). Ordre éditorial du design :
// le RÉSULTAT d'abord (la conclusion se lit comme un rapport), puis la CHAÎNE
// ÉTABLIE (sous-questions → constats), puis le plan et le journal, repliés.
// Violet : c'est la machine qui interprète.
export default function InvestigationView({
  inv,
}: {
  inv: NonNullable<ChatResponse["investigation"]>;
}) {
  return (
    <div className="space-y-5">
      {/* Résumé d'investigation — barre repliée par défaut. */}
      <details className="group">
        <summary className="flex items-center gap-2 cursor-pointer list-none rounded-card border border-line-subtle bg-bg-secondary px-4 py-2.5">
          <span className="grid place-items-center w-4 h-4 rounded-full bg-success text-white text-[9px]">✓</span>
          <span className="text-label uppercase text-ink-tertiary flex-1">
            Investigation terminée · {inv.steps.length} étape{inv.steps.length > 1 ? "s" : ""} · {inv.subject_label ?? inv.subject}
          </span>
          <span className="text-small text-brand-700 group-open:hidden">Déplier</span>
          <span className="text-small text-brand-700 hidden group-open:inline">Replier</span>
        </summary>

        <div className="mt-3 space-y-4 pl-1">
          {inv.plan.length > 0 && (
            <div className="space-y-1">
              <div className="text-label uppercase text-ink-tertiary">Plan d'investigation</div>
              <ol className="text-body space-y-1">
                {inv.plan.map((p, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-reasoning font-medium mono">{i + 1}.</span>
                    <span className="text-ink-secondary">
                      <span className="font-medium text-ink-primary">{p.title}</span> — {p.rationale}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {inv.journal?.length > 0 && (
            <details className="text-small">
              <summary className="cursor-pointer text-ink-tertiary hover:text-ink-primary">
                Journal de raisonnement ({inv.journal.length})
              </summary>
              <ol className="mt-2 space-y-1 border-l border-line pl-3">
                {inv.journal.map((j, i) => {
                  const dot =
                    j.status === "accepted" ? "text-reasoning"
                    : j.status === "rejected" ? "text-ink-tertiary"
                    : j.phase === "revision" ? "text-warning-hover"
                    : "text-line-strong";
                  return (
                    <li key={i} className="flex gap-2">
                      <span className="meta text-[10px]">{j.t}</span>
                      <span className={dot}>●</span>
                      <span className="text-ink-secondary">{j.detail}</span>
                    </li>
                  );
                })}
              </ol>
            </details>
          )}
        </div>
      </details>

      {/* RÉSULTAT — la conclusion, lue comme un rapport. Le détail (chaîne
          établie, SQL) part dans la Preuve : le centre décide, il ne détaille pas. */}
      <div className="space-y-2">
        <div className="text-label uppercase text-ink-tertiary">Résultat</div>
        <div className="text-title text-ink-primary max-w-reading">{inv.conclusion}</div>
      </div>

      {/* « Le moteur change d'avis » — révision d'hypothèse (raisonnement). */}
      {inv.revisions?.length > 0 && (
        <div className="rounded-card bg-reasoning-subtle border border-reasoning/20 p-2.5 space-y-1">
          <div className="text-label uppercase text-reasoning-hover">J'ai revu mon analyse</div>
          {inv.revisions.map((r, i) => (
            <div key={i} className="text-body text-ink-secondary">{r}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// Chaîne établie — sous-questions → constats. Vit dans la PREUVE (panneau droit),
// plus au centre : le physique et le détail technique y ont leur place.
export function InvestigationChain({
  steps,
}: {
  steps: NonNullable<ChatResponse["investigation"]>["steps"];
}) {
  if (!steps?.length) return null;
  return (
    <div className="space-y-2">
      <div className="text-label uppercase text-ink-tertiary">Chaîne établie</div>
      <div className="card divide-y divide-line-inset">
        {steps.map((s, i) => (
          <div key={i} className="px-3 py-2.5">
            <div className="flex items-start gap-2.5">
              <span className="font-mono text-[11px] text-ink-tertiary mt-0.5">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="text-body text-ink-primary">{s.question}</div>
                <div className="text-body text-ink-secondary">{s.finding}</div>
              </div>
            </div>
            <details className="mt-1 pl-[26px] text-small text-ink-tertiary">
              <summary className="cursor-pointer hover:text-ink-primary">SQL</summary>
              <pre className="mt-1 mono bg-bg-secondary border border-line-subtle rounded p-2 overflow-x-auto whitespace-pre-wrap text-ink-secondary">
                {s.sql}
              </pre>
            </details>
          </div>
        ))}
      </div>
    </div>
  );
}
