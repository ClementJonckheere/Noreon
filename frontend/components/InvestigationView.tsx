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
