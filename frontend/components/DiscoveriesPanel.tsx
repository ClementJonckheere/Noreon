"use client";

import { useEffect, useState } from "react";
import { api, Discoveries, DiscoveryItem } from "@/lib/api";

// Hiérarchie premium (retour utilisateur) : critique 🔴 / important 🟠 /
// opportunité 🟢 / information ⚪.
const LEVEL_META: Record<
  string,
  { dot: string; label: string; card: string }
> = {
  critical: { dot: "🔴", label: "Critique", card: "bg-red-500/5 border-red-500/25" },
  important: { dot: "🟠", label: "Important", card: "bg-amber-500/5 border-amber-500/25" },
  opportunity: { dot: "🟢", label: "Opportunité", card: "bg-emerald-500/5 border-emerald-500/25" },
  info: { dot: "⚪", label: "Information", card: "bg-slate-50 border-noreon-border" },
};

// « Insights » : l'analyste proactif. Une accroche qui raconte, puis des cartes
// hiérarchisées qui racontent une histoire (pas juste un chiffre brut).
export default function DiscoveriesPanel({
  connectionId,
  onAsk,
}: {
  connectionId: number;
  onAsk?: (question: string) => void;
}) {
  const [d, setD] = useState<Discoveries | null>(null);
  const [name, setName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let alive = true;
    api.me()
      .then((m) => alive && setName((m.email || "").split("@")[0]))
      .catch(() => {});
    api
      .discoveries(connectionId)
      .then((r) => alive && setD(r))
      .catch(() => alive && setD(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [connectionId]);

  async function refresh() {
    setRefreshing(true);
    try {
      setD(await api.discoveries(connectionId, true));
    } finally {
      setRefreshing(false);
    }
  }

  if (loading)
    return <div className="text-xs text-noreon-soft">Analyse proactive en cours…</div>;
  if (!d || !d.scanned || d.items.length === 0) return null;

  const lv = d.levels;
  const chips: [string, number][] = [
    ["🔴 Critique", lv.critical],
    ["🟠 Important", lv.important],
    ["🟢 Opportunité", lv.opportunity],
    ["⚪ Information", lv.info],
  ];

  return (
    <div className="card p-4 space-y-3 border border-indigo-500/25">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-semibold text-indigo-700">✨ Insights</span>
        {chips.filter(([, n]) => n > 0).map(([label, n]) => (
          <span key={label} className="badge bg-indigo-500/10 text-indigo-700">
            {n} {label}
          </span>
        ))}
        <button
          onClick={refresh}
          disabled={refreshing}
          title="Recalculer les insights"
          className="ml-auto text-noreon-soft hover:text-slate-900 disabled:opacity-50"
        >
          {refreshing ? "…" : "↻"}
        </button>
      </div>

      {/* Accroche « voici ce que j'ai remarqué » */}
      {d.headline.length > 0 && (
        <div className="text-sm bg-indigo-500/5 rounded-lg p-3 space-y-0.5">
          <div className="font-medium">
            Bonjour{name ? ` ${name}` : ""} — voici ce que j'ai remarqué :
          </div>
          {d.headline.map((h, i) => (
            <div key={i} className={i === 0 ? "font-medium" : "text-noreon-soft text-xs"}>
              {i === 0 ? "🧭 " : "↓ "}
              {h}
            </div>
          ))}
        </div>
      )}

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
  const meta = LEVEL_META[it.level] ?? LEVEL_META.info;
  return (
    <div className={`rounded-lg border p-2.5 text-xs ${meta.card}`}>
      <div className="flex items-center gap-1.5">
        <span>{meta.dot}</span>
        <span className="font-medium">{it.title}</span>
      </div>
      {/* La carte raconte une histoire, pas seulement un chiffre. */}
      <div className="mt-1 text-slate-600">{it.narrative || it.detail}</div>
      {it.suggested_question && onAsk && (
        <button
          onClick={() => onAsk(it.suggested_question!)}
          className="mt-1.5 text-indigo-700 underline decoration-dotted hover:opacity-80"
        >
          Creuser →
        </button>
      )}
    </div>
  );
}
