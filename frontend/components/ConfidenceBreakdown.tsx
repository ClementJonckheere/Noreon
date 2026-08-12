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

type State = "evaluated" | "partial" | "not_evaluated";
type Factor = {
  factor: string; contribution_pct: number; weight_pct: number; subscore_pct: number;
  state?: State; detail?: string | null;
};

// Un bloqueur critique empêche la publication même au-dessus du seuil. On lit
// l'ÉTAT auditable de chaque dimension : une qualité « non évaluée » ou « partielle »,
// ou des concepts non validés, sont des vérifications à lever — pas un simple score.
export function publishability(c: NonNullable<ChatResponse["confidence"]>, _r?: ChatResponse) {
  const bd = (c.breakdown ?? []) as Factor[];
  const st = (k: string): State => bd.find((f) => f.factor === k)?.state ?? "evaluated";
  const gaps: string[] = [];
  if (st("qualité") !== "evaluated") gaps.push("la qualité des données n'est pas encore entièrement évaluée");
  if (st("concepts") !== "evaluated") gaps.push("certains concepts métier ne sont pas validés");
  const aboveThreshold = c.percent >= THRESHOLD;
  const publishable = aboveThreshold && gaps.length === 0;
  return { publishable, gaps, aboveThreshold };
}

export default function ConfidenceBreakdown({ c, r }: { c: NonNullable<ChatResponse["confidence"]>; r?: ChatResponse }) {
  const bd = (c.breakdown ?? []) as Factor[];
  const factor = (k: string) => bd.find((f) => f.factor === k);
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

      {/* État de publication : ≥ seuil ET aucune vérification critique restante. */}
      {pub.publishable ? (
        <div className="text-label uppercase text-ink-tertiary">Au-dessus du seuil · publiable</div>
      ) : (
        <div className="state state-limit">
          <div className="state-title">{c.percent}% · vérification requise</div>
          <div className="state-body">
            {pub.aboveThreshold
              ? `La confiance dépasse le seuil, mais ${countWord(pub.gaps.length)} ${pub.gaps.length > 1 ? "restent nécessaires" : "reste nécessaire"} avant publication : ${joinGaps(pub.gaps)}.`
              : `Sous le seuil de publication de l'espace${pub.gaps.length ? ` ; de plus, ${joinGaps(pub.gaps)}` : ""}.`}
          </div>
        </div>
      )}

      {/* Les 4 dimensions métier — libellé d'ÉTAT, pas un pourcentage qui
          contredirait « non évaluée ». */}
      <ul className="space-y-1.5 pt-1">
        {BUSINESS.map((d) => {
          const f = factor(d.key);
          if (!f) return null;
          const state: State = f.state ?? "evaluated";
          return (
            <li key={d.key} className="space-y-0.5">
              <div className="flex items-center justify-between text-small">
                <span className="text-ink-secondary">{d.label}</span>
                <DimStatus state={state} pct={f.subscore_pct} />
              </div>
              <div className="h-1 rounded-full bg-line-inset overflow-hidden">
                {state === "not_evaluated" ? (
                  <div className="h-full w-full" style={{ backgroundImage: "repeating-linear-gradient(45deg, var(--border-strong) 0 3px, transparent 3px 6px)", opacity: 0.4 }} />
                ) : (
                  <div className="h-full rounded-full bg-reasoning" style={{ width: `${f.subscore_pct}%` }} />
                )}
              </div>
              {f.detail && state !== "not_evaluated" && (
                <div className="meta">{f.detail}</div>
              )}
              {state === "not_evaluated" && f.detail && (
                <div className="meta">{f.detail}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DimStatus({ state, pct }: { state: State; pct: number }) {
  if (state === "not_evaluated") return <span className="text-label uppercase text-ink-tertiary">Non évaluée</span>;
  if (state === "partial") return <span className="meta">{pct}% · partielle</span>;
  return <span className="meta">{pct}%</span>;
}

function countWord(n: number): string {
  return n === 1 ? "une vérification" : `${n === 2 ? "deux" : n} vérifications`;
}

function joinGaps(gaps: string[]): string {
  if (gaps.length <= 1) return gaps[0] ?? "";
  return `${gaps.slice(0, -1).join(", ")} et ${gaps[gaps.length - 1]}`;
}

// Contrôles techniques — pour la PREUVE (pas une dimension métier de confiance).
// « Un SQL valide peut produire une mauvaise conclusion si la sémantique est fausse. »
export function TechnicalControls({ c, r }: { c?: ChatResponse["confidence"]; r: ChatResponse }) {
  const bd = ((c?.breakdown ?? []) as Factor[]);
  const rows: { label: string; ok: boolean; detail?: string }[] = [];
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
