"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, MeasurementDetail } from "@/lib/api";

// Résultat contrôlé — ce qui transforme « −1,4 pt » en résultat AUDITABLE :
// protocole figé, fenêtres semi-ouvertes, valeurs réelles, témoins choisis AVANT
// l'observation, limites du protocole. On mesure un écart, on ne proclame pas une cause.
const RESULT: Record<string, { label: string; cls: string }> = {
  objectif_atteint: { label: "ATTEINT", cls: "text-success-hover" },
  objectif_non_atteint: { label: "NON ATTEINT", cls: "text-warning-hover" },
  inconclusif: { label: "INCONCLUSIF", cls: "text-ink-tertiary" },
  a_qualifier: { label: "À QUALIFIER", cls: "text-ink-tertiary" },
};
const TYPE_LABEL: Record<string, string> = {
  impact: "Impact", performance: "Performance", completion: "Complétude", diagnostic: "Diagnostic",
};
const pct = (x: number | null, u = "%") => (x == null ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)} ${u}`);
const num = (x: number | null) => (x == null ? "—" : Math.round(x).toLocaleString("fr-FR").replace(/ |,/g, " "));
// Fenêtre SEMI-OUVERTE affichée par sa borne incluse (portée par le backend) :
// « 29 mai → 27 juin inclus » — le jour de mise en œuvre bascule côté observation.
const day = (iso?: string | null) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "—";
const win = (w?: { from: string; to_inclusive: string } | null) =>
  w ? `${day(w.from)} → ${day(w.to_inclusive)} inclus` : "—";

export default function MeasurementProof() {
  const id = Number(useParams().id);
  const [d, setD] = useState<MeasurementDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.measurementDetail(id).then(setD).catch(() => setErr("Aucune mesure pour cette action.")); }, [id]);

  if (err) return <div className="space-y-3"><Link href="/plan" className="text-small text-ink-tertiary hover:text-ink-primary">← Plan d'action</Link><div className="card p-6 text-body text-ink-secondary">{err}</div></div>;
  if (!d) return <div className="text-body text-ink-tertiary">Chargement…</div>;

  const p = d.protocol;
  const cs = p.control_selection;
  const run = d.runs[d.runs.length - 1];

  return (
    <div className="space-y-6 fade-in max-w-3xl">
      <div className="space-y-1">
        <nav className="text-small text-ink-tertiary">
          <Link href="/plan" className="hover:text-ink-primary">Plan d'action</Link>
          <span className="mx-1.5">/</span><span>Mesure</span>
          <span className="mx-1.5">/</span><span className="text-ink-secondary">Résultat contrôlé</span>
        </nav>
        <h1 className="text-title text-ink-primary">Résultat contrôlé</h1>
        <p className="text-body text-ink-secondary">Protocole, données et comparaison ayant conduit au résultat.</p>
        <p className="text-small text-ink-tertiary">{d.action.role} · {d.action.recommendation}</p>
      </div>

      {/* PROTOCOLE figé — présentation éditoriale : mesure et type dissociés. */}
      <section className="card p-4 space-y-3">
        <h2 className="text-label uppercase text-ink-tertiary">Protocole</h2>
        <Row k="Mesure">{p.metric_label}</Row>
        <Row k="Type de protocole">{TYPE_LABEL[p.measure_type] ?? p.measure_type}</Row>
        <Row k="Traités">{p.target.join(", ")}</Row>
        {cs && <Row k="Témoins">{cs.control_ids.join(", ")}</Row>}
        <Row k="Objectif">écart contrôlé ≥ {pct(p.threshold, "pt")}</Row>
        <Row k="Mise en œuvre">{p.implemented_at ? p.implemented_at.slice(0, 10) : "—"}</Row>
      </section>

      {/* BASELINE vs OBSERVATION — les valeurs réelles, fenêtres semi-ouvertes. */}
      {run && (
        <section className="card p-4 space-y-3">
          <h2 className="text-label uppercase text-ink-tertiary">Baseline → Observation</h2>
          <table className="w-full text-body">
            <thead>
              <tr className="text-small text-ink-tertiary text-left">
                <th className="font-normal pb-1"></th>
                <th className="font-normal pb-1">Baseline<div className="meta">{win(p.baseline_window)}</div></th>
                <th className="font-normal pb-1">Observation<div className="meta">{win(run.observation_window)}</div></th>
                <th className="font-normal pb-1 text-right">Évolution</th>
              </tr>
            </thead>
            <tbody className="mono">
              <tr className="border-t border-line-inset">
                <td className="py-1.5 font-sans text-ink-secondary">Traités</td>
                <td>{num(run.baseline_target)}</td><td>{num(run.observed_target)}</td>
                <td className="text-right text-ink-primary">{pct(run.raw_delta)}</td>
              </tr>
              <tr className="border-t border-line-inset">
                <td className="py-1.5 font-sans text-ink-secondary">Témoins</td>
                <td>{num(run.baseline_control)}</td><td>{num(run.observed_control)}</td>
                <td className="text-right text-ink-primary">{pct(run.control_delta)}</td>
              </tr>
            </tbody>
          </table>
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-t border-line-inset pt-2">
            <span className="text-body text-ink-secondary">Écart contrôlé (cible − témoins)</span>
            <span className="mono text-ink-primary">{pct(run.adjusted_delta, "pts")}</span>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-body text-ink-secondary">Résultat</span>
            <span className={`font-medium ${RESULT[run.result]?.cls ?? "text-ink-tertiary"}`}>{RESULT[run.result]?.label ?? run.result}</span>
          </div>
        </section>
      )}

      {/* SÉLECTION DES TÉMOINS — figée AVANT l'observation ; critères d'appariement. */}
      {cs && (
        <section className="card p-4 space-y-3">
          <h2 className="text-label uppercase text-ink-tertiary">Sélection des témoins</h2>
          <p className="text-body text-ink-secondary max-w-reading">
            Les témoins ont été figés le <span className="text-ink-primary">{cs.selection_at?.slice(0, 10)}</span> —
            à la mise en œuvre, <span className="font-medium">avant toute observation post-action</span>. Ils ne peuvent
            donc pas avoir été choisis pour produire un résultat.
          </p>
          {/* Tableau des critères : deux CALCULÉS (niveau, tendance), le reste DÉCLARÉ. */}
          {cs.criteria && cs.criteria.length > 0 && (
            <div className="rounded-card border border-line-subtle divide-y divide-line-inset">
              {cs.criteria.map((c, i) => (
                <div key={i} className="flex items-baseline justify-between gap-3 px-3 py-1.5 text-small">
                  <span className="text-ink-secondary">{c.label}</span>
                  <span className="flex items-baseline gap-2 shrink-0">
                    <span className="text-ink-primary">{c.verdict}</span>
                    {c.score != null
                      ? <span className="mono text-ink-tertiary">{Math.round(c.score * 100)} %</span>
                      : <span className="text-ink-tertiary text-xs">déclaré</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
          {/* Vivier évalué : répond à « pourquoi ces témoins et pas d'autres ? ».
              Les retenus sont les PLUS comparables avant action ; les écartés portent
              leur motif (p. ex. un magasin de la même région déjà en recul). */}
          {cs.considered && cs.considered.length > cs.control_ids.length && (
            <div className="space-y-1.5">
              <div className="text-small text-ink-tertiary">
                {cs.n_candidates ?? cs.considered.length} magasins évalués · {cs.control_ids.length} retenus
                (les plus comparables avant action)
              </div>
              <div className="rounded-card border border-line-subtle divide-y divide-line-inset text-small">
                {cs.considered.map((c) => (
                  <div key={c.id} className="flex items-baseline gap-3 px-3 py-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 self-center ${c.retained ? "bg-brand-500" : "bg-line-strong"}`} />
                    <span className="min-w-0 flex-1">
                      <span className="text-ink-primary">{c.id}</span>
                      {c.region && <span className="text-ink-tertiary"> · {c.region}</span>}
                      {!c.retained && c.reason && <span className="text-ink-tertiary"> — {c.reason}</span>}
                    </span>
                    <span className="mono text-ink-tertiary shrink-0">
                      niv. {c.matching_score != null ? Math.round(c.matching_score * 100) : "—"} · tend. {c.pretrend_score != null ? Math.round(c.pretrend_score * 100) : "—"}
                    </span>
                    <span className={`shrink-0 text-xs uppercase ${c.retained ? "text-brand-700" : "text-ink-tertiary"}`}>
                      {c.retained ? "retenu" : "écarté"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Réserve honnête : 2 témoins réduisent le bruit de contexte, sans constituer
              un contrôle expérimental robuste. Orange = limite épistémique, pas blocage. */}
          {cs.small_group && (
            <div className="state state-limit">
              <div className="state-body">
                Groupe témoin restreint ({cs.n_control ?? cs.control_ids.length} magasins) : il réduit certains effets
                de contexte, mais ne constitue pas un contrôle expérimental robuste.
              </div>
            </div>
          )}
        </section>
      )}

      {/* LIMITES — jamais affirmatives ; puis NIVEAU DE PREUVE explicite. */}
      <section className="card p-4 space-y-3">
        <h2 className="text-label uppercase text-ink-tertiary">Limites du protocole</h2>
        {run && run.limitations.length > 0 ? (
          <ul className="list-disc pl-4 text-body text-ink-secondary space-y-0.5">{run.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
        ) : (
          <p className="text-body text-ink-secondary">Aucune anomalie majeure détectée dans le protocole.</p>
        )}
        <p className="text-body text-ink-secondary max-w-reading">
          La comparaison avec des magasins témoins réduit certains effets de contexte
          (saison, conjoncture) mais ne permet pas d'isoler tous les facteurs externes.
        </p>
        <div className="rounded-card border border-line-strong bg-bg-secondary p-3">
          <div className="text-label uppercase text-brand-700">Niveau de preuve · Résultat contrôlé</div>
          <p className="text-small text-ink-secondary mt-1 max-w-reading">
            Ce protocole compare une évolution observée à celle de témoins appariés. Il
            ne constitue pas une attribution causale complète.
          </p>
        </div>
      </section>

      {/* AUDIT — métier (concept, définition) ET technique (snapshot, protocole, hash). */}
      <section className="card p-4 space-y-2">
        <h2 className="text-label uppercase text-ink-tertiary">Audit</h2>
        <div className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-small">
          <span className="text-ink-secondary">Concept mesuré</span>
          <span className="text-right">
            {p.metric_label} · <span className="mono text-ink-tertiary">{p.metric_concept_id}</span>
            {p.metric_definition_version != null && <span className="text-ink-tertiary"> · définition {p.metric_definition_version}</span>}
          </span>
          {run?.snapshot_id && <><span className="text-ink-secondary">Snapshot des données</span><span className="text-right mono text-ink-tertiary">{run.snapshot_id}</span></>}
          <span className="text-ink-secondary">Version du protocole</span><span className="text-right mono text-ink-tertiary">v{p.protocol_version}</span>
          {p.baseline_query_hash && <><span className="text-ink-secondary">Empreinte requête baseline</span><span className="text-right mono text-ink-tertiary">{p.baseline_query_hash}</span></>}
          {run?.query_hash && <><span className="text-ink-secondary">Empreinte requête observation</span><span className="text-right mono text-ink-tertiary">{run.query_hash}</span></>}
          <span className="text-ink-secondary">Mesures effectuées</span><span className="text-right mono text-ink-tertiary">{d.runs.length}</span>
        </div>
      </section>
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-3 text-body">
      <span className="text-small text-ink-tertiary pt-0.5">{k}</span>
      <span className="text-ink-primary">{children}</span>
    </div>
  );
}
