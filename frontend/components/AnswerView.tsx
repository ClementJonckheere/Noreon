"use client";

import { ChatResponse } from "@/lib/api";
import ChartBlock from "@/components/ChartBlock";
import AddToReport from "@/components/AddToReport";
import InvestigationView from "@/components/InvestigationView";
import WhyChoices from "@/components/WhyChoices";

// Rendu d'une réponse d'analyse (partagé chat par connexion / chat d'espace).
export default function AnswerView({ r }: { r: ChatResponse }) {
  const statusColor: Record<string, string> = {
    answered: "text-emerald-700",
    clarification: "text-amber-700",
    blocked: "text-red-600",
    error: "text-red-600",
    no_schema: "text-amber-700",
  };
  return (
    <div className="space-y-4">
      {r.status !== "answered" && (
        <div className={`card p-4 text-sm ${statusColor[r.status] || ""}`}>
          <div className="font-medium capitalize mb-1">{r.status}</div>
          {r.message}
        </div>
      )}

      {r.analysis?.summary && (
        <div className="card p-4 space-y-2">
          <div className="text-sm font-medium">{r.analysis.summary}</div>
          {r.analysis.observations?.length > 0 && (
            <ul className="text-xs text-noreon-soft list-disc pl-4">
              {r.analysis.observations.map((o: string, i: number) => <li key={i}>{o}</li>)}
            </ul>
          )}
          {r.analysis.anomalies?.length > 0 && (
            <div className="text-xs bg-amber-500/10 rounded-lg p-2 space-y-1">
              <div className="font-medium text-amber-700">Anomalies détectées</div>
              <ul className="list-disc pl-4 text-amber-700">
                {r.analysis.anomalies.map((a: string, i: number) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
          {r.analysis.recommendations?.length > 0 && (
            <div className="text-xs space-y-1">
              <div className="font-medium text-sky-700">Recommandations</div>
              <ul className="list-disc pl-4 text-noreon-soft">
                {r.analysis.recommendations.map((rec: string, i: number) => <li key={i}>{rec}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {r.investigation && <InvestigationView inv={r.investigation} />}

      {r.deep && <DeepReportView d={r.deep} />}

      {r.privacy && r.privacy.values_protected > 0 && (
        <div className="text-xs text-emerald-700 bg-emerald-500/10 rounded-lg px-3 py-2">
          🛡 Privacy Engine — {Object.entries(r.privacy.protected_columns)
            .map(([c, t]) => `${c} (${t})`).join(", ")}{" "}
          : {r.privacy.values_protected} valeur(s) pseudonymisée(s).
        </div>
      )}

      {r.explanations?.length > 0 && <WhyChoices items={r.explanations} />}

      {r.confidence && (
        <div className="card p-4">
          <div className="flex items-center justify-between text-sm mb-2">
            <span className="font-medium">Indice de confiance</span>
            <span>{r.confidence.percent}%</span>
          </div>
          <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
            <div
              className={`h-full ${
                r.confidence.percent >= 80 ? "bg-emerald-400" : r.confidence.percent >= 60 ? "bg-amber-400" : "bg-red-400"
              }`}
              style={{ width: `${r.confidence.percent}%` }}
            />
          </div>
        </div>
      )}

      {r.chart && r.chart.type !== "table" && r.columns.length > 0 && (
        <ChartBlock columns={r.columns} rows={r.rows} suggestion={r.chart} />
      )}

      {r.columns.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-noreon-soft border-b border-noreon-border">
              <tr>{r.columns.map((c) => <th key={c} className="text-left px-3 py-2">{c}</th>)}</tr>
            </thead>
            <tbody>
              {r.rows.slice(0, 50).map((row, i) => (
                <tr key={i} className="border-b border-noreon-border/60">
                  {row.map((v, j) => <td key={j} className="px-3 py-1.5 mono">{String(v ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {r.sql && (
        <details className="card p-4">
          <summary className="cursor-pointer text-sm font-medium">Transparence de l’analyse</summary>
          <pre className="mt-3 mono bg-slate-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap text-xs">
            {r.sql}
          </pre>
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

function DeepReportView({ d }: { d: NonNullable<ChatResponse["deep"]> }) {
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  return (
    <div className="card p-4 space-y-3 border border-sky-500/30">
      <div className="text-sm font-semibold text-sky-700">📊 Présentation approfondie</div>
      {d.context.length > 0 && (
        <div className="text-xs text-noreon-soft space-y-1">
          {d.context.map((c, i) => <div key={i}>{c}</div>)}
        </div>
      )}
      {d.drivers.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium text-sky-700">Facteurs explicatifs</div>
          <ul className="text-xs list-disc pl-4 space-y-1">
            {d.drivers.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {d.crosstab && d.crosstab.cells.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium text-sky-700">
            Croisement : {d.crosstab.dim_a} × {d.crosstab.dim_b}
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs w-full">
              <tbody>
                {d.crosstab.cells.map((c, i) => (
                  <tr key={i} className="border-t border-noreon-border">
                    <td className="py-1 pr-3">{c.a}</td>
                    <td className="py-1 pr-3">{c.b}</td>
                    <td className="py-1 text-right mono">{fmt(c.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {d.findings.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium text-amber-700">Points d'attention</div>
          <ul className="text-xs list-disc pl-4 space-y-1 text-amber-700">
            {d.findings.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {d.recommendations.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium text-emerald-700">Recommandations métier</div>
          <ul className="text-xs list-disc pl-4 space-y-1 text-noreon-soft">
            {d.recommendations.map((x, i) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
