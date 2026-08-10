"use client";

import { ChatResponse } from "@/lib/api";

// Confiance de l'analyse — TOUJOURS violette (la machine estime sa propre
// certitude ; jamais verte). Regroupée en 4 DIMENSIONS MÉTIER ; les contrôles
// techniques (SQL, relations) vivent dans la Preuve, pas ici.
const THRESHOLD = 75;

// factor backend → dimension métier (les autres = contrôles techniques).
const BUSINESS: { key: string; label: string }[] = [
  { key: "qualité", label: "Qualité des données" },
  { key: "concepts", label: "Certitude sémantique" },
  { key: "couverture", label: "Couverture analytique" },
  { key: "hypothèses", label: "Robustesse des comparaisons" },
];
const TECHNICAL_KEYS = ["SQL", "relations"];

type Factor = { factor: string; contribution_pct: number; weight_pct: number; subscore_pct: number };

// Un bloqueur critique empêche la publication même au-dessus du seuil : qualité
// non évaluée, ou certitude sémantique au plancher (concepts seulement proposés).
export function publishability(c: NonNullable<ChatResponse["confidence"]>, r?: ChatResponse) {
  const bd = (c.breakdown ?? []) as Factor[];
  const sub = (k: string) => bd.find((f) => f.factor === k)?.subscore_pct ?? null;
  const factorsText = (c.factors ?? []).join(" ").toLowerCase();
  const gaps: string[] = [];
  if (/qualité inconnue|non évalué/.test(factorsText) || (sub("qualité") ?? 100) <= 0)
    gaps.push("qualité des données non évaluée");
  const allProposed = (r?.investigation?.concepts ?? []).length > 0 &&
    (r?.investigation?.concepts ?? []).every((x) => x.scope === "proposed");
  if (allProposed || (sub("concepts") ?? 100) <= 50)
    gaps.push("concepts non encore validés");
  const publishable = c.percent >= THRESHOLD && gaps.length === 0;
  return { publishable, gaps, aboveThreshold: c.percent >= THRESHOLD };
}

export default function ConfidenceBreakdown({ c, r }: { c: NonNullable<ChatResponse["confidence"]>; r?: ChatResponse }) {
  const bd = (c.breakdown ?? []) as Factor[];
  const sub = (k: string) => bd.find((f) => f.factor === k)?.subscore_pct ?? null;
  const pub = publishability(c, r);

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-label uppercase text-ink-tertiary">Confiance de l'analyse</span>
        <span className="metric text-reasoning">{c.percent}%</span>
      </div>

      <div className="relative">
        <div className="confidence-track">
          <div className={`confidence-fill ${pub.publishable ? "" : "confidence-fill-below"}`} style={{ width: `${Math.max(0, Math.min(100, c.percent))}%` }} />
        </div>
        <div className="absolute -top-[3px] h-[11px] w-px bg-ink-secondary" style={{ left: `${THRESHOLD}%` }} />
      </div>

      {/* État de publication : ≥ seuil ET aucun bloqueur critique. */}
      {pub.publishable ? (
        <div className="text-label uppercase text-ink-tertiary">Au-dessus du seuil · publiable</div>
      ) : (
        <div className="state state-limit">
          <div className="state-title">
            {c.percent}% · vérification requise
          </div>
          <div className="state-body">
            {pub.aboveThreshold
              ? "La confiance dépasse le seuil, mais un point critique reste à lever avant publication : "
              : "Sous le seuil de publication de l'espace. "}
            {pub.gaps.join(" · ") || "preuve insuffisante"}.
          </div>
        </div>
      )}

      {/* Les 4 dimensions métier (sous-score par dimension). */}
      <ul className="space-y-1.5 pt-1">
        {BUSINESS.map((d) => {
          const s = sub(d.key);
          if (s == null) return null;
          return (
            <li key={d.key} className="space-y-0.5">
              <div className="flex items-center justify-between text-small">
                <span className="text-ink-secondary">{d.label}</span>
                <span className="meta">{s}%</span>
              </div>
              <div className="h-1 rounded-full bg-line-inset overflow-hidden">
                <div className="h-full rounded-full bg-reasoning" style={{ width: `${s}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// Contrôles techniques — pour la PREUVE (pas une dimension métier de confiance).
// « Un SQL valide peut produire une mauvaise conclusion si la sémantique est fausse. »
export function TechnicalControls({ c, r }: { c?: ChatResponse["confidence"]; r: ChatResponse }) {
  const bd = ((c?.breakdown ?? []) as Factor[]);
  const rows: { label: string; ok: boolean; detail?: string }[] = [];
  const sqlOk = (bd.find((f) => f.factor === "SQL")?.subscore_pct ?? 100) >= 60;
  rows.push({ label: "SQL exécuté avec succès", ok: !!r.sql && r.status === "answered" });
  const relOk = bd.find((f) => f.factor === "relations")?.subscore_pct;
  if (relOk != null) rows.push({ label: "Relations vérifiées", ok: relOk >= 60, detail: `${relOk}%` });
  const checks = r.validation?.checks ?? [];
  if (checks.length) {
    const passed = checks.filter((k) => k.status === "pass").length;
    rows.push({ label: `${passed}/${checks.length} contrôles passés`, ok: passed === checks.length });
  }
  if (!rows.length) return null;
  return (
    <div className="space-y-1.5">
      <div className="text-label uppercase text-ink-tertiary">Contrôles techniques</div>
      <div className="space-y-1">
        {rows.map((row, i) => (
          <div key={i} className="flex items-center gap-2 text-body">
            <span className={`w-2 h-2 rounded-full shrink-0 ${row.ok ? "bg-reasoning" : "border border-line-strong"}`} />
            <span className="text-ink-secondary flex-1">{row.label}</span>
            {row.detail && <span className="meta">{row.detail}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
