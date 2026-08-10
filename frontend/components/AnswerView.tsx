"use client";

import { ChatResponse } from "@/lib/api";
import ChartBlock from "@/components/ChartBlock";
import AddToReport from "@/components/AddToReport";
import InvestigationView from "@/components/InvestigationView";
import WhyChoices from "@/components/WhyChoices";
import ValidationPanel from "@/components/ValidationPanel";
import MeasureChoice from "@/components/MeasureChoice";
import SimulationView from "@/components/SimulationView";
import EvidenceGraph from "@/components/EvidenceGraph";
import ConfidenceBreakdown from "@/components/ConfidenceBreakdown";
import DecisionView from "@/components/DecisionView";

// Rendu d'une réponse d'analyse (partagé chat par connexion / chat d'espace).
//
// Divulgation progressive en 3 niveaux = les trois profondeurs du produit :
//   Niveau 1 — Décision   (aéré)     : la réponse lisible + graphique + reco.
//   Niveau 2 — Comprendre (équilibré): pourquoi, hypothèses, sources, confiance.
//   Niveau 3 — Preuve     (dense)    : graphe de preuve, relecture, SQL, données.
//
// La distinction qui ne doit jamais s'effacer :
//   BLOCAGE (rouge)    — « je ne peux pas travailler » (source coupée, refus).
//   ABSTENTION (orange)— « j'ai travaillé, je ne conclus pas » (preuve faible…).

// État → bloc sémantique. « answered » ne porte pas de bandeau (et jamais de
// vert : le vert est réservé à la validation externe).
const STATUS_BLOCK: Record<string, { cls: string; title: string }> = {
  clarification: { cls: "state-abstain", title: "Je ne conclus pas" },
  unanswerable: { cls: "state-abstain", title: "Je ne conclus pas" },
  no_schema: { cls: "state-abstain", title: "Analyse impossible" },
  blocked: { cls: "state-blocker", title: "Blocage" },
  error: { cls: "state-blocker", title: "Blocage" },
};

// mode « centre » : la conversation sort « Comprendre » et « Preuve » vers le
// panneau droit contextuel — le centre reste Question → Réponse → Recommandation.
export default function AnswerView({
  r, connectionId, mode = "full",
}: {
  r: ChatResponse;
  connectionId?: number;
  mode?: "full" | "centre";
}) {
  const subject = r.investigation?.subject ?? r.tables_used?.[0];
  const block = STATUS_BLOCK[r.status];

  return (
    <div className="space-y-4 fade-in">
      {block && (
        <div className={`state ${block.cls}`}>
          <div className="state-title">{block.title}</div>
          <div className="state-body">{r.message}</div>
        </div>
      )}

      {r.analysis?.summary && (
        <div className="card p-4 space-y-2.5">
          <div className="text-subhead text-ink">{r.analysis.summary}</div>
          {r.analysis.observations?.length > 0 && (
            <ul className="text-body text-ink-2 list-disc pl-4 space-y-0.5">
              {r.analysis.observations.map((o: string, i: number) => <li key={i}>{o}</li>)}
            </ul>
          )}
          {r.analysis.anomalies?.length > 0 && (
            <div className="state state-limit">
              <div className="state-title">Limite</div>
              <ul className="state-body list-disc pl-4 space-y-0.5">
                {r.analysis.anomalies.map((a: string, i: number) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
          {r.analysis.recommendations?.length > 0 && (
            <div className="space-y-1">
              <div className="text-label uppercase text-brand-700">Recommandations</div>
              <ul className="text-body text-ink-2 list-disc pl-4 space-y-0.5">
                {r.analysis.recommendations.map((rec: string, i: number) => <li key={i}>{rec}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Niveau 1 — Décision : contenu principal + graphique. */}
      {!r.decisions && r.intent_restated && r.status === "answered" && (
        <div className="text-small text-ink-3">Objectif compris : {r.intent_restated}</div>
      )}

      {/* Observation initiale : le constat temporel, distinct de la conclusion
          causale — Noreon n'a pas encore fini d'investiguer à ce stade. */}
      {r.chronicle && r.chronicle.streak >= 2 && (
        <div className="rounded-card border border-line-subtle bg-bg-secondary px-4 py-3">
          <div className="text-label uppercase text-ink-tertiary mb-1">Observation initiale</div>
          <div className="text-body text-ink-secondary">{r.chronicle.narrative}</div>
        </div>
      )}

      {/* Réponse avant conseil : le raisonnement (Résultat + chaîne) d'abord… */}
      {r.investigation && <InvestigationView inv={r.investigation} />}

      {/* …puis seulement les décisions / recommandations qui en découlent. */}
      {r.decisions && <DecisionView d={r.decisions} connectionId={connectionId} subject={subject} />}

      {/* Sérendipité : une découverte adjacente produite par le raisonnement. */}
      {r.serendipity && <SerendipityCard s={r.serendipity} />}

      {r.simulation && <SimulationView s={r.simulation} />}
      {r.deep && <DeepReportView d={r.deep} />}
      {r.measure_options && <MeasureChoice m={r.measure_options} />}

      {r.chart && r.chart.type !== "table" && r.columns.length > 0 && (
        <ChartBlock columns={r.columns} rows={r.rows} suggestion={r.chart} />
      )}

      {r.privacy && r.privacy.values_protected > 0 && (
        <div className="text-small text-success-hover bg-success-subtle rounded-card px-3 py-2">
          Privacy Engine — {Object.entries(r.privacy.protected_columns)
            .map(([c, t]) => `${c} (${t})`).join(", ")}{" "}
          : {r.privacy.values_protected} valeur(s) pseudonymisée(s).
        </div>
      )}

      {/* Niveau 2 — Comprendre (équilibré, déplié à la demande). En mode
          « centre », déplacé vers le panneau droit contextuel. */}
      {mode === "full" && (r.validation || r.confidence || r.explanations?.length > 0 || r.proof ||
        r.sources?.length > 0 || r.self_critique?.length > 0) && (
        <details className="card px-4 py-3 density-even" open={r.status !== "answered"}>
          <summary className="cursor-pointer text-subhead text-ink-2 hover:text-ink">
            Comprendre — hypothèses, pourquoi, confiance
          </summary>
          <div className="mt-3 space-y-3">
            {r.validation && <ValidationPanel v={r.validation} />}
            {(r.explanations?.length > 0 || r.proof) && (
              <WhyChoices items={r.explanations} proof={r.proof} />
            )}
            {r.confidence && <ConfidenceBreakdown c={r.confidence} r={r} />}
            {r.sources?.length > 0 && <SourcesBar sources={r.sources} />}
            {r.self_critique?.length > 0 && (
              <div className="state state-limit">
                <div className="state-title">Ce qui pourrait remettre en question cette conclusion</div>
                <ul className="state-body space-y-0.5">
                  {r.self_critique.map((c, i) => {
                    const f = c.trim();
                    const s = /^(suppose|considère|retient|écarte|ignore)\b/i.test(f) ? `Cette analyse ${f}` : f;
                    const t = s.charAt(0).toUpperCase() + s.slice(1);
                    return <li key={i}>{/[.!?]$/.test(t) ? t : `${t}.`}</li>;
                  })}
                </ul>
              </div>
            )}
          </div>
        </details>
      )}

      {/* Niveau 3 — Preuve (dense) : graphe de preuve, données, SQL. En mode
          « centre », déplacé vers le panneau droit contextuel. */}
      {mode === "full" && (r.sql || r.columns.length > 0) && (
        <details className="card px-4 py-3 density-dense">
          <summary className="cursor-pointer text-subhead text-ink-2 hover:text-ink">
            Preuve & raisonnement — graphe, données, SQL
          </summary>
          <div className="mt-3 space-y-3">
            <EvidenceGraph r={r} />
            {r.columns.length > 0 && (
              <div className="card overflow-x-auto">
                <div className="text-label uppercase px-3 py-2 text-ink-3">
                  Données ({r.row_count} ligne{r.row_count > 1 ? "s" : ""})
                </div>
                <table className="w-full text-body">
                  <thead className="text-ink-3 border-b border-line">
                    <tr>{r.columns.map((c) => <th key={c} className="text-left px-3 py-2 font-medium mono">{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {r.rows.slice(0, 50).map((row, i) => (
                      <tr key={i} className="border-b border-line-subtle">
                        {row.map((v, j) => <td key={j} className="px-3 py-1.5 mono text-ink-2">{String(v ?? "")}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {r.sql && (
              <pre className="mono bg-paper-2 border border-line-subtle rounded-card p-3 overflow-x-auto whitespace-pre-wrap text-small text-ink-2">
                {r.sql}
              </pre>
            )}

            {/* Métadonnées d'exécution. */}
            <div className="space-y-3">
              {r.tables_used?.length > 0 && (
                <div>
                  <div className="text-label uppercase text-ink-3 mb-1.5">Tables utilisées</div>
                  <div className="flex flex-wrap gap-1.5">
                    {r.tables_used.map((t) => (
                      <span key={t} className="tag tag-neutral">
                        <span className="mono">{t}</span>
                        {r.table_quality?.[t] != null && (
                          <span className="text-ink-3">· qualité {r.table_quality[t]}%</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {r.columns_used?.length > 0 && (
                <MetaList label="Colonnes utilisées" items={r.columns_used} />
              )}
              {r.assumptions?.length > 0 && (
                <div>
                  <div className="text-label uppercase text-ink-3 mb-1.5">Hypothèses retenues</div>
                  <ul className="list-disc pl-4 text-body text-ink-2 space-y-0.5">
                    {r.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap gap-4 meta">
                {r.duration_ms != null && <span>{r.duration_ms} ms</span>}
                {r.estimated_cost != null && (
                  <span>coût estimé {Math.round(r.estimated_cost).toLocaleString()}</span>
                )}
                <span>{r.row_count} ligne(s)</span>
              </div>
              {r.warnings?.length > 0 && (
                <div className="text-small text-warning-hover">{r.warnings.join(" · ")}</div>
              )}
            </div>
          </div>
        </details>
      )}

      {r.status === "answered" && (
        <div className="pt-1">
          <AddToReport response={r} title={r.question} />
        </div>
      )}
    </div>
  );
}

// Sérendipité — le moteur signale spontanément une découverte adjacente. Violet :
// c'est le raisonnement qui l'a produite. Ton mesuré, jamais une certitude.
function SerendipityCard({ s }: { s: NonNullable<ChatResponse["serendipity"]> }) {
  return (
    <div className="card p-4 border-l-[3px] border-l-reason space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="tag tag-reason">Découverte inattendue</span>
        {s.score_label && <span className="tag tag-neutral">{s.score_label}</span>}
      </div>
      <div className="text-body text-ink-2">
        En analysant votre question, les données ont aussi révélé, sur{" "}
        <span className="mono">{s.table}</span>, un point qui pourrait mériter votre attention :
      </div>
      <div className="text-subhead text-ink">{s.title}</div>
      <div className="text-body text-ink-3">{s.detail}</div>
    </div>
  );
}

function MetaList({ label, items }: { label: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-label uppercase text-ink-3 mb-1.5">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((i) => (
          <span key={i} className="tag tag-neutral"><span className="mono">{i}</span></span>
        ))}
      </div>
    </div>
  );
}

// Sources citées — d'où vient chaque chiffre (comme un article scientifique).
function SourcesBar({ sources }: { sources: ChatResponse["sources"] }) {
  return (
    <div className="flex items-center gap-2 flex-wrap text-small text-ink-3">
      <span className="text-label uppercase">Sources</span>
      {sources.map((s) => (
        <span
          key={s.table}
          className="tag tag-neutral"
          title={s.quality_pct !== null ? `Qualité ${s.quality_pct}%` : undefined}
        >
          <span className="mono">{s.table}</span>
          <span className="text-ink-3"> · {s.role}</span>
          {s.quality_pct !== null && <span className="text-ink-3"> · {s.quality_pct}%</span>}
        </span>
      ))}
    </div>
  );
}

function DeepReportView({ d }: { d: NonNullable<ChatResponse["deep"]> }) {
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  return (
    <div className="card p-4 space-y-3 border-l-[3px] border-l-brand-600">
      <div className="flex items-center gap-2">
        <span className="tag tag-brand">Approfondissement</span>
        <span className="text-heading text-ink">Présentation détaillée</span>
      </div>
      {d.context.length > 0 && (
        <div className="text-body text-ink-3 space-y-1">
          {d.context.map((c, i) => <div key={i}>{c}</div>)}
        </div>
      )}
      {d.drivers.length > 0 && (
        <div className="space-y-1">
          <div className="text-label uppercase text-ink-3">Facteurs explicatifs</div>
          <ul className="text-body text-ink-2 list-disc pl-4 space-y-1">
            {d.drivers.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {d.crosstab && d.crosstab.cells.length > 0 && (
        <div className="space-y-1">
          <div className="text-label uppercase text-ink-3">
            Croisement : {d.crosstab.dim_a} × {d.crosstab.dim_b}
          </div>
          <div className="overflow-x-auto">
            <table className="text-body w-full">
              <tbody>
                {d.crosstab.cells.map((c, i) => (
                  <tr key={i} className="border-t border-line-subtle">
                    <td className="py-1 pr-3 text-ink-2">{c.a}</td>
                    <td className="py-1 pr-3 text-ink-2">{c.b}</td>
                    <td className="py-1 text-right mono text-ink">{fmt(c.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {d.findings.length > 0 && (
        <div className="state state-limit">
          <div className="state-title">Points d'attention</div>
          <ul className="state-body list-disc pl-4 space-y-1">
            {d.findings.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {d.recommendations.length > 0 && (
        <div className="space-y-1">
          <div className="text-label uppercase text-brand-700">Recommandations métier</div>
          <ul className="text-body text-ink-2 list-disc pl-4 space-y-1">
            {d.recommendations.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
