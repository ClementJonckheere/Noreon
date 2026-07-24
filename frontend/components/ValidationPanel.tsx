"use client";

import { ValidationReport } from "@/lib/api";

// Validation Engine — la « relecture ». Noreon vérifie sa propre analyse avant
// de la montrer : hypothèses retenues, contrôles, score de fiabilité du rapport.
const CHECK_META: Record<string, { icon: string; cls: string }> = {
  pass: { icon: "✓", cls: "text-emerald-600" },
  warn: { icon: "⚠", cls: "text-amber-600" },
  fail: { icon: "✗", cls: "text-red-600" },
};
const FACTOR_META: Record<string, { icon: string; cls: string }> = {
  ok: { icon: "✓", cls: "text-emerald-600" },
  warn: { icon: "⚠", cls: "text-amber-600" },
  fail: { icon: "✗", cls: "text-red-600" },
};

export default function ValidationPanel({ v }: { v: ValidationReport }) {
  const stars = "★".repeat(v.reliability_stars) + "☆".repeat(5 - v.reliability_stars);
  const scoreCls =
    v.reliability_percent >= 85
      ? "text-emerald-600"
      : v.reliability_percent >= 65
      ? "text-amber-600"
      : "text-red-600";

  return (
    <div className="card p-4 space-y-3 border border-emerald-500/25">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-emerald-700">🧪 Relecture</span>
        <div className="flex items-center gap-2">
          <span className={`text-lg font-semibold ${scoreCls}`}>{v.reliability_percent}%</span>
          <span className="text-amber-500" title="Fiabilité du rapport">{stars}</span>
        </div>
      </div>

      {/* « Je ne peux pas conclure » — distinct de « impossible de répondre ». */}
      {v.verdict === "cannot_conclude" && v.verdict_note && (
        <div className="text-xs bg-amber-500/10 text-amber-800 rounded-lg p-2.5">
          <span className="font-medium">Je ne peux pas conclure — </span>
          {v.verdict_note}
        </div>
      )}

      {/* Hypothèses retenues, rendues explicites. */}
      {v.hypotheses.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-700 mb-1">Hypothèses retenues</div>
          <ul className="text-xs text-slate-600 space-y-0.5">
            {v.hypotheses.map((h, i) => (
              <li key={i}>• {h}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Facteurs de fiabilité (rapport entier, pas seulement le SQL). */}
      {v.reliability_factors.length > 0 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {v.reliability_factors.map((f, i) => {
            const m = FACTOR_META[f.status] ?? FACTOR_META.warn;
            return (
              <span key={i} className={`text-xs ${m.cls}`}>
                {m.icon} {f.label}
              </span>
            );
          })}
        </div>
      )}

      {/* Contrôles détaillés (dépliables). */}
      <details>
        <summary className="cursor-pointer text-xs text-noreon-soft">
          Détail des contrôles ({v.checks.length})
        </summary>
        <ul className="mt-2 space-y-1.5">
          {v.checks.map((c, i) => {
            const m = CHECK_META[c.status] ?? CHECK_META.warn;
            return (
              <li key={i} className="text-xs flex gap-2">
                <span className={m.cls}>{m.icon}</span>
                <span>
                  <span className="font-medium">{c.label}.</span> <span className="text-slate-600">{c.detail}</span>
                </span>
              </li>
            );
          })}
        </ul>
      </details>
    </div>
  );
}
