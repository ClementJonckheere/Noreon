"use client";

import { ChatResponse } from "@/lib/api";

// Indice de confiance — TOUJOURS violet : c'est la machine qui estime sa propre
// certitude. La barre ne devient jamais verte ; seul un humain valide (le vert
// est réservé à la validation externe). Un seuil de publication est marqué.
const THRESHOLD = 75;

// Teintes de la barre empilée : famille violet + neutres, jamais vert/rouge —
// une composante n'est ni « bonne » ni « mauvaise », elle contribue.
const FACTOR_TINT: Record<string, string> = {
  qualité: "bg-reason",
  concepts: "bg-brand-400",
  relations: "bg-brand-600",
  SQL: "bg-reason-hover",
  couverture: "bg-brand-300",
  hypothèses: "bg-line-strong",
};

export default function ConfidenceBreakdown({ c }: { c: NonNullable<ChatResponse["confidence"]> }) {
  const bd = c.breakdown ?? [];
  return (
    <div className="card p-4 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-label uppercase text-ink-3">Confiance de Noreon</span>
        <span className="metric text-reason">{c.percent}%</span>
      </div>

      {/* Piste violette + repère de seuil de publication. */}
      <div className="relative">
        <div className="confidence-track">
          <div className="confidence-fill" style={{ width: `${Math.max(0, Math.min(100, c.percent))}%` }} />
        </div>
        <div
          className="absolute -top-0.5 h-2.5 w-px bg-line-strong"
          style={{ left: `${THRESHOLD}%` }}
          title={`Seuil de publication ${THRESHOLD}%`}
        />
      </div>
      <div className="flex items-center justify-between text-label uppercase text-ink-3">
        <span>{c.percent >= THRESHOLD ? "Au-dessus du seuil" : "Sous le seuil de l'espace"}</span>
        <span>Seuil {THRESHOLD}%</span>
      </div>

      {bd.length > 0 && (
        <>
          <div className="flex h-2 rounded-full overflow-hidden bg-paper-2 mt-1">
            {bd.map((f) => (
              <div
                key={f.factor}
                className={FACTOR_TINT[f.factor] || "bg-line-strong"}
                style={{ width: `${f.contribution_pct}%` }}
                title={`${f.factor} : ${f.contribution_pct}% (poids ${f.weight_pct}%, sous-score ${f.subscore_pct}%)`}
              />
            ))}
          </div>
          <ul className="text-small space-y-0.5">
            {bd.map((f) => (
              <li key={f.factor} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-ink-2">
                  <span className={`inline-block w-2 h-2 rounded-full ${FACTOR_TINT[f.factor] || "bg-line-strong"}`} />
                  {f.factor}
                </span>
                <span className="meta">
                  {f.contribution_pct}%
                  <span className="text-ink-3/60"> / {f.weight_pct}%</span>
                  {f.subscore_pct < 100 && <span className="text-warning-hover"> · {f.subscore_pct}%</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {c.factors?.length > 0 && <div className="text-small text-ink-3">{c.factors.join(" · ")}</div>}
    </div>
  );
}
