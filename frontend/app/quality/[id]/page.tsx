"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { api, Connection, QualityScore } from "@/lib/api";
import { useSession } from "@/lib/session";

// Fiche de confiance d'une SOURCE — remplace le « Score qualité » global opaque
// par des dimensions auditables (fraîcheur, complétude, cohérence, validité,
// unicité), les incidents concrets et les conclusions qu'ils fragilisent.
// Ici le VERT est légitime : un contrôle qui passe est une validation externe
// de la donnée (pas une estimation de la machine).

const GOOD = 0.9, WARN = 0.75;
// Ordre d'affichage métier (le backend expose ces libellés).
const DIM_ORDER = ["Fraîcheur", "Complétude", "Cohérence", "Validité", "Unicité"];

function tone(score: number) {
  if (score >= GOOD) return { cls: "text-success", bar: "bg-success", label: "conforme" };
  if (score >= WARN) return { cls: "text-warning", bar: "bg-warning", label: "à surveiller" };
  return { cls: "text-blocker", bar: "bg-blocker", label: "à corriger" };
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
          <h1 className="text-title text-ink-primary">Confiance de la source</h1>
          <p className="text-body text-ink-secondary max-w-reading">
            Les contrôles auditables qui tournent avant chaque réponse — jusqu'où Noreon
            peut se fier à cette source, dimension par dimension.
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
          {/* Confiance globale — moyenne des tables profilées. */}
          <div className="card p-4 flex items-center gap-4">
            <div className={`metric text-[28px] ${tone(model.base).cls}`}>{pct(model.base)}</div>
            <div className="min-w-0">
              <div className="text-subhead text-ink-primary">Confiance globale de la source</div>
              <div className="meta">{model.tablesScored} table(s) profilée(s) · {model.columnsScored} colonne(s) contrôlée(s)</div>
            </div>
          </div>

          {/* Dimensions auditables. */}
          <section className="space-y-2">
            <h2 className="text-label uppercase text-ink-tertiary">Dimensions de confiance</h2>
            <div className="grid gap-2 md:grid-cols-2">
              {model.dims.map((d) => (
                <div key={d.name} className="card p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-subhead text-ink-primary">{d.name}</span>
                    <span className={`meta ${tone(d.score).cls}`}>{pct(d.score)} · {tone(d.score).label}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-line-inset overflow-hidden">
                    <div className={`h-full rounded-full ${tone(d.score).bar}`} style={{ width: pct(d.score) }} />
                  </div>
                  {d.worst && <div className="meta">{d.worst}</div>}
                </div>
              ))}
            </div>
          </section>

          {/* Incidents concrets — ce qui tire la confiance vers le bas. */}
          <section className="space-y-2">
            <h2 className="text-label uppercase text-ink-tertiary">Incidents</h2>
            {model.incidents.length === 0 ? (
              <div className="card p-4 flex items-center gap-2 text-body text-ink-secondary">
                <span className="w-2 h-2 rounded-full bg-success shrink-0" />
                Aucun incident : tous les contrôles passent au-dessus du seuil.
              </div>
            ) : (
              <div className="card divide-y divide-line-inset">
                {model.incidents.map((it, i) => (
                  <div key={i} className={`px-4 py-2.5 flex items-start gap-3 ${highlightTable && it.table === highlightTable ? "bg-warning-subtle" : ""}`}>
                    <span className={`w-2 h-2 rounded-full shrink-0 mt-1.5 ${tone(it.score).bar}`} />
                    <div className="min-w-0 flex-1">
                      <div className="mono text-small text-ink-primary">{it.ref}</div>
                      <div className="text-body text-ink-secondary">{it.detail}</div>
                    </div>
                    <span className={`meta shrink-0 ${tone(it.score).cls}`}>{pct(it.score)}</span>
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
                  portent une réserve de confiance tant que ces contrôles ne repassent pas au-dessus du seuil.
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

type Model = {
  hasScores: boolean;
  base: number;
  tablesScored: number;
  columnsScored: number;
  dims: { name: string; score: number; worst?: string }[];
  incidents: { ref: string; table: string; detail: string; score: number }[];
  impacted: string[];
};

function buildModel(scores: QualityScore[]): Model {
  const cols = scores.filter((s) => s.level === "column");
  const rels = scores.filter((s) => s.level === "relation");
  const tables = scores.filter((s) => s.level === "table");
  const base = scores.find((s) => s.level === "base");

  // Agrégation des dimensions colonne → dimension source.
  const agg: Record<string, { sum: number; n: number; worst?: { detail: string; score: number } }> = {};
  for (const c of cols) {
    for (const d of c.dimensions ?? []) {
      if (!d.applicable || d.score == null) continue;
      const a = (agg[d.name] ??= { sum: 0, n: 0 });
      a.sum += d.score; a.n += 1;
      if (!a.worst || d.score < a.worst.score) a.worst = { detail: d.detail, score: d.score };
    }
  }
  const dims = DIM_ORDER
    .filter((name) => agg[name]?.n)
    .map((name) => ({
      name,
      score: agg[name].sum / agg[name].n,
      worst: agg[name].worst && agg[name].worst.score < GOOD ? agg[name].worst.detail : undefined,
    }));

  // Incidents : colonnes/relations sous le seuil, les plus faibles d'abord.
  const incidents = [
    ...cols.map((c) => ({
      ref: `${c.table_name}.${c.column_name}`, table: c.table_name ?? "", detail: c.detail, score: c.score,
    })),
    ...rels.map((r) => ({
      ref: r.relation_ref ?? "relation", table: r.table_name ?? "", detail: r.detail, score: r.score,
    })),
  ].filter((x) => x.score < GOOD).sort((a, b) => a.score - b.score).slice(0, 10);

  // Conclusions impactées : tables dont le score passe sous le seuil.
  const impacted = tables.filter((t) => t.score < WARN && t.table_name).map((t) => t.table_name as string);

  return {
    hasScores: cols.length > 0 || tables.length > 0,
    base: base?.score ?? (tables.length ? tables.reduce((s, t) => s + t.score, 0) / tables.length : 1),
    tablesScored: tables.length,
    columnsScored: cols.length,
    dims, incidents, impacted,
  };
}
