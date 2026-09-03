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
          {/* Violet, pas vert : c'est un PROCESSUS machine terminé, pas une
              conclusion validée par un tiers (le vert = validation externe). */}
          <span className="grid place-items-center w-4 h-4 rounded-full bg-reasoning text-white text-[9px]">✓</span>
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

      {/* Graphique principal — Observer avant de démontrer : la courbe de la
          mesure rend la conclusion tangible (rythme Résultat → Vérification →
          Recommandations). Compact, pas un dashboard. */}
      <MiniTrend inv={inv} />

      {/* VÉRIFICATION AUTOMATIQUE — factuelle et chiffrée : ce qui a été testé et
          pourquoi une piste a été écartée. Pas un journal introspectif (« à
          première vue… mais en isolant… ») : des vérifications auditables. */}
      {inv.verification ? (
        <VerificationBlock v={inv.verification} />
      ) : (
        inv.revisions?.length > 0 && (
          <div className="rounded-card border border-line-subtle bg-bg-secondary p-3 space-y-1">
            <div className="text-label uppercase text-reasoning-hover">Vérification automatique</div>
            {inv.revisions.map((r, i) => (
              <div key={i} className="text-body text-ink-secondary">{r}</div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

// Mini-courbe temporelle de la mesure — SVG inline (offline, sans dépendance).
// Neutre (observation), jamais verte/violette : c'est la donnée brute. La fenêtre
// récente est mise en avant en encre pleine ; l'historique reste estompé.
const _MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
function fmtMonth(label: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(label);
  return m ? `${_MONTHS_FR[parseInt(m[2], 10) - 1]} ${m[1]}` : label;
}
function fmtNum(v: number): string {
  return Math.round(v).toLocaleString("fr-FR").replace(/ |,/g, " ");
}

function MiniTrend({ inv }: { inv: NonNullable<ChatResponse["investigation"]> }) {
  const rows = (inv.trend_rows ?? []) as any[][];
  if (rows.length < 2) return null;
  const pts = rows.map((r) => ({ label: String(r[0]), v: Number(r[1]) || 0 }));
  const vals = pts.map((p) => p.v);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const W = 100, H = 30, pad = 1.5;
  const x = (i: number) => pad + (i / (pts.length - 1)) * (W - 2 * pad);
  const y = (v: number) => pad + (1 - (v - min) / span) * (H - 2 * pad);
  const path = (from: number) => pts.slice(from).map((p, i) => `${i ? "L" : "M"}${x(from + i).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  // L'annotation illustre EXACTEMENT la comparaison de la conclusion : le total
  // de la période (premier → dernier point = « −8 % au total »). Le trait renforcé
  // met en avant le recul récent (du sommet à la fin), sans changer le chiffre.
  const first = pts[0], last = pts[pts.length - 1];
  const from = first;
  const deltaPct = first.v ? Math.round(((last.v - first.v) / first.v) * 100) : 0;
  let peak = 0;
  for (let i = 1; i < pts.length; i++) if (pts[i].v > pts[peak].v) peak = i;
  const wStart = peak < pts.length - 1 ? peak : Math.max(0, pts.length - 4);
  const metricLabel = inv.measure_label_concept ?? "Chiffre d'affaires";
  return (
    <div className="rounded-card border border-line-subtle bg-bg-secondary p-3 space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-label uppercase text-ink-tertiary">{metricLabel} · évolution</span>
        <span className="meta">séquence étudiée</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-16" role="img" aria-label={`Évolution de ${metricLabel}`}>
        <path d={path(0)} fill="none" stroke="var(--border-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        <path d={path(wStart)} fill="none" stroke="var(--text-primary)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between items-baseline meta">
        <span>{fmtMonth(from.label)} · {fmtNum(from.v)}</span>
        <span className="text-ink-secondary">
          {fmtMonth(last.label)} · <span className="font-medium text-ink-primary">{fmtNum(last.v)}</span>
          {deltaPct !== 0 && <span className={deltaPct < 0 ? "text-ink-secondary" : "text-ink-secondary"}> · {deltaPct > 0 ? "+" : ""}{deltaPct} %</span>}
        </span>
      </div>
    </div>
  );
}

function VerificationBlock({ v }: { v: NonNullable<NonNullable<ChatResponse["investigation"]>["verification"]> }) {
  const max = Math.max(1, ...(v.tested ?? []).map((t) => t.pct));
  const isWinner = (t: { dimension: string; segment: string }) =>
    t.dimension === v.winner.dimension && t.segment === v.winner.segment;
  return (
    <div className="rounded-card border border-line-subtle bg-bg-secondary p-3 space-y-2.5">
      <div className="text-label uppercase text-reasoning-hover">Vérification automatique</div>
      <div className="text-body text-ink-secondary max-w-reading">{v.text}</div>
      {(v.tested?.length ?? 0) > 0 && (
        <>
        {/* Légende explicite : toutes les valeurs sont la MÊME mesure
            (contribution à la variation), jamais une part de CA. */}
        <div className="meta pt-0.5">{v.measure_label ?? "part de la variation concentrée par axe"}</div>
        <ul className="space-y-1">
          {v.tested.map((t, i) => {
            const win = isWinner(t);
            return (
              <li key={i} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5">
                <span className={`text-small ${win ? "text-ink-primary font-medium" : "text-ink-secondary"}`}>
                  {t.dimension}{t.segment ? ` · ${t.segment}` : ""}
                  {win && <span className="ml-2 tag text-reasoning border-reasoning/30">retenu</span>}
                </span>
                <span className={`mono text-small tabular-nums text-right ${win ? "text-reasoning" : "text-ink-tertiary"}`}>{t.pct}%</span>
                <div className="col-span-2 h-1 rounded-full bg-line-inset overflow-hidden">
                  <div className={`h-full rounded-full ${win ? "bg-reasoning" : "bg-line-strong"}`} style={{ width: `${(t.pct / max) * 100}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
        </>
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
