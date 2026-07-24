"use client";

import { ChatResponse } from "@/lib/api";

// Rendu du raisonnement de l'agent : plan → étapes (sous-questions + constats) →
// synthèse. Chaque étape est justifiée et porte son SQL (transparence « preuve »).
export default function InvestigationView({
  inv,
}: {
  inv: NonNullable<ChatResponse["investigation"]>;
}) {
  return (
    <div className="card p-4 space-y-4 border border-indigo-500/30">
      <div className="text-sm font-semibold text-indigo-700">
        🧭 Raisonnement de l'agent — {inv.steps.length} étape(s) sur « {inv.subject} »
      </div>

      {/* Plan annoncé */}
      {inv.plan.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium">Plan d'investigation</div>
          <ol className="text-xs space-y-1">
            {inv.plan.map((p, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-indigo-600 font-medium">{i + 1}.</span>
                <span>
                  <span className="font-medium">{p.title}</span>
                  <span className="text-noreon-soft"> — {p.rationale}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Étapes exécutées */}
      <div className="space-y-2">
        <div className="text-sm font-medium">Sous-questions & constats</div>
        {inv.steps.map((s, i) => (
          <div key={i} className="bg-white/60 rounded-lg border border-noreon-border p-2 space-y-1">
            <div className="text-xs font-medium">
              {i + 1}. {s.question}
            </div>
            <div className="text-xs">{s.finding}</div>
            <details className="text-[11px] text-noreon-soft">
              <summary className="cursor-pointer">Pourquoi & SQL</summary>
              <div className="mt-1">{s.rationale}</div>
              <pre className="mt-1 mono bg-slate-100 rounded p-2 overflow-x-auto whitespace-pre-wrap">
                {s.sql}
              </pre>
            </details>
          </div>
        ))}
      </div>

      {/* « Le moteur change d'avis » — révision d'hypothèse. */}
      {inv.revisions?.length > 0 && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/25 p-2.5 space-y-1">
          <div className="text-xs font-medium text-amber-800">🔄 J'ai revu mon analyse</div>
          {inv.revisions.map((r, i) => (
            <div key={i} className="text-xs text-amber-800">{r}</div>
          ))}
        </div>
      )}

      {/* Journal de raisonnement (experts) — timeline horodatée. */}
      {inv.journal?.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-noreon-soft">
            🕑 Journal de raisonnement ({inv.journal.length})
          </summary>
          <ol className="mt-2 space-y-1 border-l border-noreon-border pl-3">
            {inv.journal.map((j, i) => {
              const dot =
                j.status === "accepted" ? "text-emerald-600"
                : j.status === "rejected" ? "text-red-500"
                : j.phase === "revision" ? "text-amber-600"
                : "text-slate-400";
              return (
                <li key={i} className="flex gap-2">
                  <span className="mono text-[10px] text-slate-400">{j.t}</span>
                  <span className={dot}>●</span>
                  <span className="text-slate-600">{j.detail}</span>
                </li>
              );
            })}
          </ol>
        </details>
      )}

      {/* Synthèse */}
      <div className="space-y-1">
        <div className="text-sm font-medium text-indigo-700">Synthèse</div>
        <div className="text-sm">{inv.conclusion}</div>
        {inv.key_drivers.length > 0 && (
          <div className="text-xs text-noreon-soft">
            Facteurs classés : {inv.key_drivers.join(" · ")}
          </div>
        )}
      </div>

      {inv.recommendations.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium text-emerald-700">Prochaines actions</div>
          <ul className="text-xs list-disc pl-4 space-y-1 text-noreon-soft">
            {inv.recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
