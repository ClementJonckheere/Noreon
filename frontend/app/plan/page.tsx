"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, PlanItem } from "@/lib/api";
import { useSession } from "@/lib/session";

// Plan d'action — ce qu'on décide de FAIRE. Les décisions retenues depuis les
// analyses, suivies dans le temps : retenue → mise en œuvre → (mesure du résultat).
// « Réussie » ne se déclare pas d'un clic : c'est la mesure qui la pose.

const STATUS = {
  retained: { label: "Retenue", cls: "text-brand-700 bg-brand-50 border-brand-200" },
  implemented: { label: "Mise en œuvre", cls: "text-reason bg-reason-subtle border-reason/30" },
  successful: { label: "Résultat mesuré", cls: "text-success-hover bg-success-subtle border-success-border" },
  abandoned: { label: "Abandonnée", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle" },
} as const;

export default function PlanPage() {
  const { caps } = useSession();
  const [items, setItems] = useState<PlanItem[] | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);

  async function load() {
    setItems(await api.plan(showClosed).catch(() => []));
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [showClosed]);

  async function advance(it: PlanItem, status: string) {
    setBusy(it.id);
    try { await api.planUpdate(it.id, { status }); await load(); }
    finally { setBusy(null); }
  }

  const active = (items ?? []).filter((i) => i.status === "retained" || i.status === "implemented");
  const closed = (items ?? []).filter((i) => i.status === "successful" || i.status === "abandoned");

  return (
    <div className="space-y-6 fade-in">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-title text-ink-primary">Plan d'action</h1>
          <p className="text-body text-ink-secondary max-w-reading">
            Ce qu'on décide de faire — les décisions retenues depuis les analyses, leur mise
            en œuvre et l'effet mesuré.
          </p>
        </div>
        <label className="text-small text-ink-tertiary flex items-center gap-1.5 shrink-0 mt-1">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          Afficher les actions closes
        </label>
      </header>

      {items === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : (items.length === 0) ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucune action retenue</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Une décision entre ici quand vous la retenez depuis une réponse d'analyse.
          </p>
          {caps.askQuestions && <div className="pt-2"><Link href="/" className="btn-secondary">Composer une analyse</Link></div>}
        </div>
      ) : (
        <div className="space-y-6">
          {active.length > 0 && (
            <section className="space-y-2.5">
              <h2 className="text-label uppercase text-ink-tertiary">En cours ({active.length})</h2>
              {active.map((it) => (
                <PlanCard key={it.id} it={it} busy={busy === it.id} onAdvance={advance} canDecide={caps.decideAction} />
              ))}
            </section>
          )}
          {showClosed && closed.length > 0 && (
            <section className="space-y-2.5">
              <h2 className="text-label uppercase text-ink-tertiary">Closes ({closed.length})</h2>
              {closed.map((it) => (
                <PlanCard key={it.id} it={it} busy={busy === it.id} onAdvance={advance} canDecide={caps.decideAction} />
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function PlanCard({
  it, busy, onAdvance, canDecide,
}: {
  it: PlanItem; busy: boolean; onAdvance: (it: PlanItem, s: string) => void; canDecide: boolean;
}) {
  const st = STATUS[it.status];
  const closed = it.status === "successful" || it.status === "abandoned";
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2 text-small text-ink-tertiary">
            <span>{it.role}</span>
            {it.source_name && <><span>·</span><span className="mono">{it.source_name}</span></>}
          </div>
          <div className="text-body text-ink-primary">{it.recommendation}</div>
        </div>
        <span className={`tag border shrink-0 ${st.cls}`}>{st.label}</span>
      </div>
      {it.note && <div className="meta">{it.note}</div>}
      {canDecide && !closed && (
        <div className="flex flex-wrap gap-2 pt-1">
          {it.status === "retained" && (
            <button disabled={busy} onClick={() => onAdvance(it, "implemented")} className="btn-secondary btn-sm">
              Passer en mise en œuvre
            </button>
          )}
          {it.status === "implemented" && (
            <Link href={`/conversations`} className="btn-secondary btn-sm" title="La réussite se pose par la mesure, pas d'un clic">
              Mesurer le résultat →
            </Link>
          )}
          <button disabled={busy} onClick={() => onAdvance(it, "abandoned")} className="btn-ghost btn-sm text-ink-tertiary">
            Abandonner
          </button>
        </div>
      )}
    </div>
  );
}
