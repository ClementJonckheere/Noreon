"use client";

import { useEffect, useState } from "react";
import { api, ProductMetrics } from "@/lib/api";

// Observabilité produit — Noreon mesure son propre fonctionnement.
// Deux familles : QUALITÉ (rassure le client, pilote le produit) et COÛTS.
const USAGE_LABEL: Record<string, string> = {
  insight_drill: "Insights creusés",
  chart_export: "Graphiques exportés",
  report_open: "Rapports ouverts",
  concept_use: "Concepts utilisés",
  whatif_run: "Simulations lancées",
};

export default function MetricsPage() {
  const [m, setM] = useState<ProductMetrics | null>(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .metrics({ days })
      .then((r) => alive && (setM(r), setErr(null)))
      .catch((e) => alive && setErr(e.message || "Erreur"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [days]);

  const pct = (x: number | null | undefined) =>
    x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`;
  const ms = (x: number | null | undefined) =>
    x === null || x === undefined ? "—" : x >= 1000 ? `${(x / 1000).toFixed(2)} s` : `${Math.round(x)} ms`;
  const num = (x: number | null | undefined) =>
    x === null || x === undefined ? "—" : x.toLocaleString("fr-FR");

  return (
    <div className="space-y-6 fade-in">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg font-semibold">Observabilité</h1>
          <p className="text-sm text-noreon-soft">
            Noreon mesure la qualité de son propre travail — aucune donnée métier brute.
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="input w-auto"
        >
          <option value={7}>7 jours</option>
          <option value={30}>30 jours</option>
          <option value={90}>90 jours</option>
        </select>
      </div>

      {loading && <div className="text-sm text-noreon-soft">Chargement…</div>}
      {err && <div className="card p-4 text-sm text-red-600">{err}</div>}

      {m && (
        <>
          <div className="text-xs text-noreon-soft">
            {num(m.total_analyses)} analyse(s) sur {m.window_days} jours.
          </div>

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-indigo-700">Qualité</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <Tile label="Temps moyen d'analyse" value={ms(m.quality.avg_duration_ms)} />
              <Tile label="Confiance moyenne" value={pct(m.quality.avg_confidence)} good />
              <Tile label="Questions résolues" value={pct(m.quality.resolution_rate)} good />
              <Tile label="Clarifications demandées" value={pct(m.quality.clarification_rate)} />
              <Tile label="SQL validés" value={pct(m.quality.sql_validation_rate)} good />
            </div>
          </section>

          {Object.keys(m.usage?.by_event || {}).length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-fuchsia-700">Usage — ce qui sert le plus</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                {Object.entries(m.usage.by_event).map(([ev, n]) => (
                  <Tile key={ev} label={USAGE_LABEL[ev] || ev} value={num(n)} />
                ))}
              </div>
            </section>
          )}

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-sky-700">Coûts</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <Tile label="Appels LLM" value={num(m.costs.llm_calls)} />
              <Tile label="Jetons LLM" value={num(m.costs.llm_tokens_total)} hint="heuristique hors-ligne = 0" />
              <Tile label="Temps LLM moyen" value={ms(m.costs.llm_ms_avg)} />
              <Tile label="Temps SQL moyen" value={ms(m.costs.avg_sql_ms)} />
              <Tile
                label="Cache utilisé"
                value={pct(m.costs.cache_hit_rate)}
                hint={`${num(m.costs.cache_hits)} hits / ${num(m.costs.cache_misses)} miss`}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  hint,
  good,
}: {
  label: string;
  value: string;
  hint?: string;
  good?: boolean;
}) {
  return (
    <div className="card p-4">
      <div className={`text-2xl font-semibold ${good ? "text-emerald-600" : "text-slate-800"}`}>
        {value}
      </div>
      <div className="mt-1 text-xs text-noreon-soft">{label}</div>
      {hint && <div className="text-[11px] text-slate-400 mt-0.5">{hint}</div>}
    </div>
  );
}
