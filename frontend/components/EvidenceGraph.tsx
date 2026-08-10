"use client";

import { ChatResponse } from "@/lib/api";
import Icon from "@/components/ui/Icon";

// Evidence Graph — toute la chaîne logique en un seul arbre :
// Question → Hypothèses → Tables → Jointures → SQL → Résultat → Conclusion.
// La FORCE DE PREUVE se lit au poids du repère (violet raisonnement → neutre →
// creux), jamais en vert/rouge : le vert reste la validation externe, le rouge
// le blocage. La force n'est ni une validation ni un blocage.
type Strength = "strong" | "medium" | "weak";

function Mark({ level }: { level?: Strength }) {
  if (!level) return <span className="w-2 h-2 shrink-0" />;
  if (level === "strong") return <span className="w-2 h-2 rounded-full bg-reasoning shrink-0" title="preuve forte" />;
  if (level === "medium") return <span className="w-2 h-2 rounded-full bg-line-strong shrink-0" title="preuve moyenne" />;
  return <span className="w-2 h-2 rounded-full border border-line-strong shrink-0" title="preuve faible" />;
}

type Node = { label: string; detail?: string; level?: Strength; children?: Node[] };

function buildTree(r: ChatResponse): Node[] {
  const nodes: Node[] = [];

  const hyps = r.validation?.hypotheses ?? [];
  if (hyps.length > 0) {
    nodes.push({ label: "Hypothèses", level: r.proof?.level, children: hyps.map((h) => ({ label: h })) });
  }

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

  if ((r.sources?.length ?? 0) > 1) {
    const join = r.validation?.checks.find((c) => c.key === "join_fanout");
    nodes.push({
      label: "Jointures",
      level: join?.status === "warn" ? "medium" : "strong",
      detail: join?.detail,
    });
  }

  if (r.proof) {
    nodes.push({ label: "Preuve", level: r.proof.level, children: r.proof.steps.map((s) => ({ label: s })) });
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
  return (
    <div>
      <div className="flex gap-2 items-center" style={{ paddingLeft: depth * 14 }}>
        <Mark level={n.level} />
        <span className="text-body font-medium text-ink-primary">{n.label}</span>
        {n.detail && (
          <span className="text-ink-tertiary text-small truncate max-w-[34ch] mono" title={n.detail}>
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
    <div className="card p-4 space-y-2 border-l-[3px] border-l-reasoning">
      <div className="flex items-center gap-2">
        <Icon name="concepts" className="w-4 h-4 text-reasoning" />
        <span className="text-subhead text-ink-primary">Graphe de preuve</span>
      </div>
      {/* Force de preuve = poids du repère, pas une couleur sémantique. */}
      <div className="text-small text-ink-tertiary flex gap-3 items-center">
        <span className="flex items-center gap-1.5"><Mark level="strong" />forte</span>
        <span className="flex items-center gap-1.5"><Mark level="medium" />moyenne</span>
        <span className="flex items-center gap-1.5"><Mark level="weak" />faible</span>
      </div>
      <div className="space-y-1 pt-1">
        <div className="flex gap-2 items-center">
          <Icon name="search" className="w-3.5 h-3.5 text-ink-tertiary shrink-0" />
          <span className="text-body font-medium text-ink-primary">Question</span>
          <span className="text-ink-tertiary text-small truncate max-w-[40ch]">{r.question}</span>
        </div>
        {tree.map((n, i) => <NodeRow key={i} n={n} depth={1} />)}
      </div>
    </div>
  );
}
