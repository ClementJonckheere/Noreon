"use client";

import { useEffect, useState } from "react";
import { api, Discoveries, DiscoveryItem } from "@/lib/api";

const CAT_META: Record<string, { icon: string; label: string }> = {
  anomaly: { icon: "⚠", label: "Anomalie" },
  trend: { icon: "📈", label: "Tendance" },
  suspicious_column: { icon: "🔎", label: "Colonne suspecte" },
  incoherent_relation: { icon: "🔗", label: "Relation incohérente" },
};

const SEV_COLOR: Record<string, string> = {
  high: "bg-red-500/10 text-red-700 border-red-500/20",
  medium: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  low: "bg-slate-100 text-slate-600 border-noreon-border",
};

// Panneau proactif : « voici ce qu'un analyste aurait remarqué ». Cliquer une
// découverte lance la question de creusement dans le chat.
export default function DiscoveriesPanel({
  connectionId,
  onAsk,
}: {
  connectionId: number;
  onAsk?: (question: string) => void;
}) {
  const [d, setD] = useState<Discoveries | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api
      .discoveries(connectionId)
      .then((r) => alive && setD(r))
      .catch(() => alive && setD(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [connectionId]);

  if (loading)
    return <div className="text-xs text-noreon-soft">Analyse proactive en cours…</div>;
  if (!d || !d.scanned || d.items.length === 0) return null;

  const c = d.counts;
  const chips = [
    ["anomalies", c.anomalies, "anomalie(s)"],
    ["trends", c.trends, "tendance(s)"],
    ["suspicious_columns", c.suspicious_columns, "colonne(s) suspecte(s)"],
    ["incoherent_relations", c.incoherent_relations, "relation(s) incohérente(s)"],
  ] as const;

  return (
    <div className="card p-4 space-y-3 border border-indigo-500/25">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-indigo-700">🧭 Découvertes</span>
        {chips.filter(([, n]) => n > 0).map(([k, n, label]) => (
          <span key={k} className="badge bg-indigo-500/10 text-indigo-700">
            {n} {label}
          </span>
        ))}
      </div>
      <div className="grid sm:grid-cols-2 gap-2">
        {d.items.map((it, i) => (
          <DiscoveryCard key={i} it={it} onAsk={onAsk} />
        ))}
      </div>
    </div>
  );
}

function DiscoveryCard({
  it,
  onAsk,
}: {
  it: DiscoveryItem;
  onAsk?: (q: string) => void;
}) {
  const meta = CAT_META[it.category] ?? { icon: "•", label: it.category };
  return (
    <div className={`rounded-lg border p-2 text-xs ${SEV_COLOR[it.severity]}`}>
      <div className="font-medium">
        {meta.icon} {it.title}
      </div>
      <div className="opacity-80 mt-0.5">{it.detail}</div>
      {it.suggested_question && onAsk && (
        <button
          onClick={() => onAsk(it.suggested_question!)}
          className="mt-1 underline decoration-dotted hover:opacity-80"
        >
          Creuser : « {it.suggested_question} »
        </button>
      )}
    </div>
  );
}
