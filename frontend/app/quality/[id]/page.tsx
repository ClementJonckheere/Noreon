"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, Connection, QualityScore } from "@/lib/api";
import { useSession } from "@/lib/session";

// Qualité d'une SOURCE — un ÉTAT explicable, pas une note globale opaque. Une
// source n'a pas besoin d'une « note » ; elle a un état, dimension par dimension.
// Couleur : le VERT = contrôle passé (validation externe de la donnée). L'ORANGE
// = réserve / obsolescence (jamais bloquant). Le ROUGE est réservé à l'opérationnel
// (source indisponible, accès refusé) — hors de ces contrôles.

const CONFORM = 0.9;
const DIM_ORDER = ["Fraîcheur", "Complétude", "Cohérence", "Validité", "Unicité"];

function dimTone(conform: boolean) {
  return conform
    ? { cls: "text-success", bar: "bg-success", label: "conforme" }
    : { cls: "text-warning", bar: "bg-warning", label: "à surveiller" };
}
const pct = (s: number) => `${Math.round(s * 100)}%`;

export default function QualitySourcePage() {
  const { id } = useParams<{ id: string }>();
  const connId = Number(id);
  const highlightTable = useSearchParams().get("table");
  const { caps } = useSession();

  const [conn, setConn] = useState<Connection | null>(null);
  const [scores, setScores] = useState<QualityScore[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const [c, s] = await Promise.all([
      api.getConnection(connId).catch(() => null),
      api.quality(connId).catch(() => [] as QualityScore[]),
    ]);
    setConn(c); setScores(s);
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [connId]);

  async function runControls() {
    setRunning(true); setError(null);
    try { await api.runQuality(connId); await load(); }
    catch (e: any) { setError(e?.message ?? "Le contrôle a échoué."); }
    finally { setRunning(false); }
  }

  const model = useMemo(() => buildModel(scores ?? []), [scores]);

  return (
    <div className="space-y-6 fade-in">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 text-small text-ink-tertiary">
            <Link href="/quality" className="hover:text-ink-primary">Qualité</Link>
            <span>/</span>
            <span className="text-ink-secondary truncate">{conn?.name ?? `Source ${connId}`}</span>
          </div>
          <h1 className="text-title text-ink-primary">Qualité de la source</h1>
          <p className="text-body text-ink-secondary max-w-reading">
            Les contrôles auditables qui tournent avant chaque réponse. Une source n'a pas
            de « note » — elle a un état, dimension par dimension.
          </p>
        </div>
        {caps.inspectQuality && scores !== null && (
          <button onClick={runControls} disabled={running} className="btn-secondary shrink-0">
            {running ? "Contrôle en cours…" : model.hasScores ? "Relancer les contrôles" : "Lancer les contrôles"}
          </button>
        )}
      </header>

      {error && <div className="state state-blocker"><div className="state-body">{error}</div></div>}

      {scores === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : !model.hasScores ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucun contrôle n'a encore tourné</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Aucune donnée n'est pas la même chose qu'aucun problème. Lancez les contrôles
            pour que Noreon mesure la fraîcheur, la complétude et la cohérence de cette source.
          </p>
          {caps.inspectQuality && (
            <div className="pt-2"><button onClick={runControls} disabled={running} className="btn-secondary">
              {running ? "Contrôle en cours…" : "Lancer les contrôles"}
            </button></div>
          )}
        </div>
      ) : (
        <>
          {/* État multidimensionnel — PAS de note globale. */}
          <div className="card p-4 space-y-1">
            <div className="text-label uppercase text-ink-tertiary">État de la source</div>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-heading text-ink-primary">
                {model.conformCount} dimension{model.conformCount > 1 ? "s" : ""} conforme{model.conformCount > 1 ? "s" : ""}
              </span>
              {model.weak.length > 0 && (
                <span className="text-heading text-warning-hover">
                  {model.weak.length} à surveiller
                </span>
              )}
            </div>
            <div className="meta">
              {model.tablesScored} table(s) profilée(s) · {model.columnsScored} colonne(s) contrôlée(s)
              {model.weak.length > 0 ? ` · réserve : ${model.weak.join(", ")}` : " · tout est conforme"}
            </div>
          </div>

          {/* Dimensions auditables. */}
          <section className="space-y-2">
            <h2 className="text-label uppercase text-ink-tertiary">Dimensions</h2>
            <div className="grid gap-2 md:grid-cols-2">
              {model.dims.map((d) => {
                const t = dimTone(d.conform);
                return (
                  <div key={d.name} className="card p-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-subhead text-ink-primary">{d.name}</span>
                      <span className={`meta ${t.cls}`}>{pct(d.score)} · {t.label}</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-line-inset overflow-hidden">
                      <div className={`h-full rounded-full ${t.bar}`} style={{ width: pct(d.score) }} />
                    </div>
                    {d.worst && <div className="meta">{d.worst}</div>}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Incidents = OBJETS (quoi · sévérité · depuis), pas des scores. */}
          <section className="space-y-2">
            <h2 className="text-label uppercase text-ink-tertiary">Incidents</h2>
            {model.incidents.length === 0 ? (
              <div className="card p-4 flex items-center gap-2 text-body text-ink-secondary">
                <span className="w-2 h-2 rounded-full bg-success shrink-0" />
                Aucun incident : tous les contrôles passent au-dessus du seuil.
              </div>
            ) : (
              <div className="space-y-2">
                {model.incidents.map((it, i) => (
                  <div key={i} className={`card p-3 space-y-1 ${highlightTable && it.table === highlightTable ? "border-warning-border" : ""}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono text-body text-ink-primary">{it.ref}</span>
                      <span className="tag tag-warning shrink-0">{it.dimension} · réserve</span>
                    </div>
                    <div className="text-body text-ink-secondary">{it.detail}</div>
                    {it.since && <div className="meta">Dernière valeur observée : {it.since}</div>}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Conclusions impactées — le pont Trust → Décision. */}
          {model.impacted.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-label uppercase text-ink-tertiary">Conclusions impactées</h2>
              <div className="state state-limit">
                <div className="state-body">
                  Les réponses qui s'appuient sur{" "}
                  {model.impacted.map((t, i) => (
                    <span key={t}><span className="mono">{t}</span>{i < model.impacted.length - 1 ? ", " : ""}</span>
                  ))}{" "}
                  portent une réserve tant que ces contrôles ne repassent pas au-dessus du seuil.
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

type Incident = { ref: string; table: string; dimension: string; detail: string; since: string | null; score: number };
type Model = {
  hasScores: boolean;
  conformCount: number;
  weak: string[];
  tablesScored: number;
  columnsScored: number;
  dims: { name: string; score: number; conform: boolean; worst?: string }[];
  incidents: Incident[];
  impacted: string[];
};

const MONTHS = ["", "janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
function sinceOf(detail: string): string | null {
  const m = /(\d{4})-(\d{2})-(\d{2})/.exec(detail || "");
  return m ? `${parseInt(m[3], 10)} ${MONTHS[parseInt(m[2], 10)]} ${m[1]}` : null;
}

function buildModel(scores: QualityScore[]): Model {
  const cols = scores.filter((s) => s.level === "column");
  const tables = scores.filter((s) => s.level === "table");

  const agg: Record<string, { sum: number; n: number; worst?: { detail: string; score: number } }> = {};
  for (const c of cols) {
    for (const d of c.dimensions ?? []) {
      if (!d.applicable || d.score == null) continue;
      const a = (agg[d.name] ??= { sum: 0, n: 0 });
      a.sum += d.score; a.n += 1;
      if (!a.worst || d.score < a.worst.score) a.worst = { detail: d.detail, score: d.score };
    }
  }
  const dims = DIM_ORDER.filter((name) => agg[name]?.n).map((name) => {
    const score = agg[name].sum / agg[name].n;
    return { name, score, conform: score >= CONFORM, worst: agg[name].worst && agg[name].worst!.score < CONFORM ? agg[name].worst!.detail : undefined };
  });

  // Incidents = objets : dimension la plus faible de chaque colonne sous le seuil.
  const incidents: Incident[] = [];
  for (const c of cols) {
    const applicable = (c.dimensions ?? []).filter((d) => d.applicable && d.score != null);
    if (!applicable.length) continue;
    const worst = applicable.reduce((a, b) => (b.score! < a.score! ? b : a));
    if (worst.score! >= CONFORM) continue;
    incidents.push({
      ref: `${c.table_name}.${c.column_name}`, table: c.table_name ?? "",
      dimension: worst.name, detail: worst.detail, since: sinceOf(worst.detail), score: worst.score!,
    });
  }
  incidents.sort((a, b) => a.score - b.score);

  return {
    hasScores: cols.length > 0 || tables.length > 0,
    conformCount: dims.filter((d) => d.conform).length,
    weak: dims.filter((d) => !d.conform).map((d) => d.name),
    tablesScored: tables.length,
    columnsScored: cols.length,
    dims,
    incidents: incidents.slice(0, 12),
    impacted: tables.filter((t) => t.score < 0.75 && t.table_name).map((t) => t.table_name as string),
  };
}
