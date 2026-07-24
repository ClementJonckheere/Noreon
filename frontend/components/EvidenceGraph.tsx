"use client";

import { ChatResponse } from "@/lib/api";

// Evidence Graph — toute la chaîne logique en un seul arbre :
// Question → Hypothèses → Tables → Jointures → SQL → Résultat → Conclusion.
// Chaque maillon porte son NIVEAU DE PREUVE (🟢 forte / 🟡 moyenne / 🔴 faible).
const LEVEL: Record<string, { dot: string; cls: string }> = {
  strong: { dot: "🟢", cls: "text-emerald-700" },
  medium: { dot: "🟡", cls: "text-amber-700" },
  weak: { dot: "🔴", cls: "text-red-600" },
};

type Node = { label: string; detail?: string; level?: "strong" | "medium" | "weak"; children?: Node[] };

function buildTree(r: ChatResponse): Node[] {
  const nodes: Node[] = [];

  // Hypothèses (contexte + mesure), niveau = celui de la preuve de table.
  const hyps = r.validation?.hypotheses ?? [];
  if (hyps.length > 0) {
    nodes.push({
      label: "Hypothèses",
      level: r.proof?.level,
      children: hyps.map((h) => ({ label: h })),
    });
  }

  // Tables mobilisées (avec leur niveau de preuve).
  if (r.sources?.length > 0) {
    nodes.push({
      label: "Tables",
      children: r.sources.map((s) => ({
        label: s.table,
        detail: `${s.role}${s.quality_pct !== null ? ` · qualité ${s.quality_pct}%` : ""}`,
        level: s.level,
      })),
    });
  }

  // Jointures (si plusieurs tables).
  if ((r.sources?.length ?? 0) > 1) {
    const join = r.validation?.checks.find((c) => c.key === "join_fanout");
    nodes.push({
      label: "Jointures",
      level: join?.status === "warn" ? "medium" : "strong",
      detail: join?.detail,
    });
  }

  // Preuve du choix de table (couverture / qualité / concept).
  if (r.proof) {
    nodes.push({
      label: "Preuve",
      level: r.proof.level,
      children: r.proof.steps.map((s) => ({ label: s })),
    });
  }

  if (r.sql) nodes.push({ label: "SQL", detail: r.sql, level: "strong" });

  nodes.push({
    label: "Résultat",
    detail: `${r.row_count} ligne${r.row_count > 1 ? "s" : ""}`,
    level: r.row_count > 0 ? "strong" : "weak",
  });

  const conclusion = r.analysis?.summary || r.message;
  if (conclusion) nodes.push({ label: "Conclusion", detail: conclusion });

  return nodes;
}

function NodeRow({ n, depth }: { n: Node; depth: number }) {
  const meta = n.level ? LEVEL[n.level] : null;
  return (
    <div>
      <div className="flex gap-2 items-baseline" style={{ paddingLeft: depth * 14 }}>
        <span className="text-noreon-border select-none">{depth > 0 ? "└─" : ""}</span>
        {meta && <span className="select-none">{meta.dot}</span>}
        <span className={`font-medium ${meta?.cls ?? ""}`}>{n.label}</span>
        {n.detail && (
          <span className="text-noreon-soft text-xs truncate max-w-[36ch] mono" title={n.detail}>
            {n.detail}
          </span>
        )}
      </div>
      {n.children?.map((c, i) => <NodeRow key={i} n={c} depth={depth + 1} />)}
    </div>
  );
}

export default function EvidenceGraph({ r }: { r: ChatResponse }) {
  const tree = buildTree(r);
  if (tree.length === 0) return null;
  return (
    <div className="card p-4 space-y-2 border border-indigo-500/25">
      <div className="text-sm font-semibold text-indigo-700">🕸️ Graphe de preuve</div>
      <div className="text-[11px] text-noreon-soft flex gap-3">
        <span>🟢 preuve forte</span>
        <span>🟡 moyenne</span>
        <span>🔴 faible</span>
      </div>
      <div className="text-xs space-y-1">
        <div className="flex gap-2 items-baseline">
          <span className="select-none">❓</span>
          <span className="font-medium">Question</span>
          <span className="text-noreon-soft truncate max-w-[40ch]">{r.question}</span>
        </div>
        {tree.map((n, i) => <NodeRow key={i} n={n} depth={1} />)}
      </div>
    </div>
  );
}
