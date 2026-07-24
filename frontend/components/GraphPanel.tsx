"use client";

// Knowledge Graph (Module 6) — graphe navigable des entités métier.
// Nœuds : tables (nom métier si concept-entité validé, volumétrie, score
// qualité). Arêtes : relations documentées (FK déclarée / inférée / validée,
// cardinalité, taux d'intégrité). Les relations inférées se valident ici,
// avec la même boucle humaine que le dictionnaire métier.

import { useEffect, useRef, useState } from "react";
import { api, Graph, GraphEdge } from "@/lib/api";

const EDGE_STYLE: Record<string, { color: string; type: "solid" | "dashed"; label: string }> = {
  declared: { color: "#199e70", type: "solid", label: "FK déclarée" },
  validated: { color: "#3987e5", type: "solid", label: "FK validée" },
  inferred: { color: "#c98500", type: "dashed", label: "FK inférée" },
};

function qualityColor(q: number | null): string {
  if (q == null) return "#9fb3d1";
  if (q >= 0.9) return "#199e70";
  if (q >= 0.7) return "#c98500";
  return "#e66767";
}

export default function GraphPanel({ id }: { id: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    try {
      setGraph(await api.graph(id));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    if (!graph || !ref.current) return;
    let disposed = false;
    import("echarts").then((echarts) => {
      if (disposed || !ref.current) return;
      chartRef.current?.dispose();
      const chart = echarts.init(ref.current);

      const maxRows = Math.max(1, ...graph.nodes.map((n) => n.rows ?? 1));
      const nodes = graph.nodes.map((n) => ({
        id: n.table,
        name: n.entity ? `${n.entity}\n(${n.name})` : n.name,
        symbolSize: 30 + 35 * Math.sqrt((n.rows ?? 1) / maxRows),
        itemStyle: {
          color: "#1c2c4d",
          borderColor: qualityColor(n.quality),
          borderWidth: 3,
        },
        label: { show: true, color: "#e2e8f0", fontSize: 12, lineHeight: 16 },
        tooltip: {
          formatter:
            `<b>${n.table}</b><br/>` +
            (n.entity ? `Entité métier : ${n.entity}<br/>` : "") +
            (n.concepts.length ? `Concepts : ${n.concepts.join(", ")}<br/>` : "") +
            `${n.columns} colonnes · ~${n.rows ?? "?"} lignes` +
            (n.quality != null ? `<br/>Score qualité : ${Math.round(n.quality * 100)}%` : ""),
        },
      }));

      const edges = graph.edges
        .filter((e) => e.status !== "rejected")
        .map((e) => {
          const style = EDGE_STYLE[e.kind] ?? EDGE_STYLE.inferred;
          return {
            source: e.from,
            target: e.to,
            lineStyle: { color: style.color, type: style.type, width: 2, curveness: 0.15 },
            tooltip: {
              formatter:
                `<b>${e.from}.${e.from_column} → ${e.to}.${e.to_column}</b><br/>` +
                `${style.label} · confiance ${Math.round(e.confidence * 100)}%` +
                (e.cardinality ? `<br/>Cardinalité : ${e.cardinality}` : "") +
                (e.integrity_ratio != null
                  ? `<br/>Intégrité : ${(e.integrity_ratio * 100).toFixed(1)}%`
                  : "") +
                (e.rationale ? `<br/><i>${e.rationale}</i>` : ""),
            },
          };
        });

      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          backgroundColor: "#1c2437",
          borderColor: "rgba(255,255,255,0.08)",
          textStyle: { color: "#e2e8f0", fontSize: 12 },
        },
        series: [
          {
            type: "graph",
            layout: "force",
            roam: true,
            draggable: true,
            force: { repulsion: 900, edgeLength: 170, gravity: 0.12 },
            emphasis: { focus: "adjacency" },
            nodes,
            edges,
          },
        ],
      });
      chartRef.current = chart;
    });
    return () => {
      disposed = true;
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, [graph]);

  async function review(e: GraphEdge, action: "validate" | "reject") {
    try {
      await api.relationReview(id, e.id, action);
      setNotice(
        action === "validate"
          ? "Relation validée : elle guide désormais les jointures avec un statut confirmé."
          : "Relation rejetée : elle ne sera plus utilisée pour les jointures.",
      );
      load();
    } catch (err: any) {
      setNotice(`Erreur : ${err.message}`);
    }
  }

  if (error)
    return (
      <div className="text-sm text-amber-700 bg-amber-500/10 rounded-lg p-3">
        {error}
      </div>
    );
  if (!graph) return <div className="text-noreon-soft">Chargement…</div>;

  const pending = graph.edges.filter((e) => e.kind === "inferred" && e.status === "proposed");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-xs text-noreon-soft">
        <span><span style={{ color: "#199e70" }}>━</span> FK déclarée</span>
        <span><span style={{ color: "#3987e5" }}>━</span> FK validée</span>
        <span><span style={{ color: "#c98500" }}>┅</span> FK inférée (à valider)</span>
        <span>Bordure du nœud = score qualité · taille = volumétrie</span>
      </div>
      <div className="card">
        <div ref={ref} className="w-full" style={{ height: 480 }} />
      </div>

      {notice && (
        <div className="text-sm text-noreon-soft bg-slate-100 rounded-lg p-3">{notice}</div>
      )}

      {pending.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">
            Relations inférées à valider ({pending.length})
          </h3>
          {pending.map((e) => (
            <div
              key={e.id}
              className="card p-3 flex flex-wrap items-center justify-between gap-2 text-xs"
            >
              <div>
                <span className="mono">
                  {e.from}.{e.from_column} → {e.to}.{e.to_column}
                </span>
                <span className="ml-2 text-noreon-soft">
                  confiance {Math.round(e.confidence * 100)}%
                  {e.cardinality && ` · ${e.cardinality}`}
                  {e.integrity_ratio != null &&
                    ` · intégrité ${(e.integrity_ratio * 100).toFixed(1)}%`}
                </span>
                {e.rationale && (
                  <div className="mt-1 text-[11px] text-indigo-700">🧩 {e.rationale}</div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  className="btn bg-emerald-500/20 text-emerald-700 hover:bg-emerald-500/30"
                  onClick={() => review(e, "validate")}
                >
                  Valider
                </button>
                <button
                  className="btn bg-red-500/20 text-red-600 hover:bg-red-500/30"
                  onClick={() => review(e, "reject")}
                >
                  Rejeter
                </button>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
