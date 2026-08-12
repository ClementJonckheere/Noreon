"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, PlanItem } from "@/lib/api";
import { useSession } from "@/lib/session";

// Plan d'action — ce qu'on décide de FAIRE. Les décisions retenues depuis les
// analyses, suivies dans le temps : retenue → mise en œuvre → (mesure du résultat).
// « Réussie » ne se déclare pas d'un clic : c'est la mesure qui la pose.

// Une action HUMAINE mise en œuvre se lit en BLEU (« on agit »), jamais en violet
// (réservé au raisonnement machine). « Résultat mesuré » est posé par la mesure.
const STATUS = {
  retained: { label: "Retenue", cls: "text-brand-700 bg-brand-50 border-brand-200" },
  implemented: { label: "Mise en œuvre", cls: "text-brand-700 bg-brand-50 border-brand-300" },
  measured: { label: "Mesurée", cls: "text-ink-secondary bg-bg-secondary border-line-subtle" },
  abandoned: { label: "Abandonnée", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle" },
  closed: { label: "Suivi clos", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle" },
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

  async function measure(it: PlanItem) {
    setBusy(it.id);
    try { await api.planMeasure(it.id); await load(); }
    finally { setBusy(null); }
  }

  const active = (items ?? []).filter((i) => i.status === "retained" || i.status === "implemented" || i.status === "measured");
  const closed = (items ?? []).filter((i) => i.status === "abandoned" || i.status === "closed");

  return (
    <div className="space-y-6 fade-in">
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-title text-ink-primary">Plan d'action</h1>
          <p className="text-body text-ink-secondary max-w-reading">
            Ce qu'on décide de faire — les décisions retenues depuis les analyses, leur mise
            en œuvre et le résultat mesuré.
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
                <PlanCard key={it.id} it={it} busy={busy === it.id} onAdvance={advance} onMeasure={measure} canDecide={caps.decideAction} />
              ))}
            </section>
          )}
          {showClosed && closed.length > 0 && (
            <section className="space-y-2.5">
              <h2 className="text-label uppercase text-ink-tertiary">Closes ({closed.length})</h2>
              {closed.map((it) => (
                <PlanCard key={it.id} it={it} busy={busy === it.id} onAdvance={advance} onMeasure={measure} canDecide={caps.decideAction} />
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}

const pct = (x: number | null, unit = "%") => (x == null ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)} ${unit}`);
const RESULT: Record<string, { label: string; cls: string }> = {
  objectif_atteint: { label: "atteint", cls: "text-success-hover" },
  objectif_non_atteint: { label: "non atteint", cls: "text-warning-hover" },
  inconclusif: { label: "inconclusif", cls: "text-ink-tertiary" },
  a_qualifier: { label: "à qualifier", cls: "text-ink-tertiary" },
};

function PlanCard({
  it, busy, onAdvance, onMeasure, canDecide,
}: {
  it: PlanItem; busy: boolean; onAdvance: (it: PlanItem, s: string) => void; onMeasure: (it: PlanItem) => void; canDecide: boolean;
}) {
  const st = STATUS[it.status];
  const closed = it.status === "abandoned" || it.status === "closed";
  const m = it.measurement;
  const run = m?.latest_run ?? null;
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2 text-small text-ink-tertiary">
            <span>{it.role}</span>
            {it.analysis_label && <><span>·</span><span>Analyse : {it.analysis_label}</span></>}
          </div>
          <div className="text-body text-ink-primary">{it.recommendation}</div>
        </div>
        <span className={`tag border shrink-0 ${st.cls}`}>{st.label}</span>
      </div>
      {it.note && <div className="meta">{it.note}</div>}

      {/* Résultat CONTRÔLÉ — jamais une causalité proclamée : cible, écart vs
          témoins, objectif atteint/non atteint, puis les limites du protocole. */}
      {run && run.result !== "inconclusif" && (
        <div className="rounded-card border border-line-subtle bg-bg-secondary p-3 space-y-1.5">
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
            <span className="text-small">
              <span className="text-ink-tertiary">Résultat mesuré · </span>
              <span className="mono text-ink-primary">{pct(run.raw_delta)}</span>
            </span>
            {run.adjusted_delta != null && (
              <span className="text-small">
                <span className="text-ink-tertiary">Écart vs témoins · </span>
                <span className="mono text-ink-primary">{pct(run.adjusted_delta, "pts")}</span>
              </span>
            )}
            <span className="text-small">
              <span className="text-ink-tertiary">Objectif {pct(m!.threshold)} · </span>
              <span className={`font-medium ${RESULT[run.result].cls}`}>{RESULT[run.result].label}</span>
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="meta">Mesuré à J+{run.horizon_days}{m!.has_control ? " · groupe témoin apparié" : " · sans témoin"}.</span>
            <Link href={`/plan/${it.id}`} className="text-small text-brand-700 hover:text-brand-800">Voir la mesure →</Link>
          </div>
        </div>
      )}
      {run && (run.result === "inconclusif" || run.result === "a_qualifier") && (
        <div className="state state-limit">
          <div className="state-body flex items-center justify-between gap-2">
            <span>{run.limitations[0] ?? "Mesure à qualifier."}</span>
            <Link href={`/plan/${it.id}`} className="text-brand-700 hover:text-brand-800 underline shrink-0">Voir la mesure →</Link>
          </div>
        </div>
      )}

      {canDecide && !closed && (
        <div className="flex flex-wrap gap-2 pt-1">
          {it.status === "retained" && (
            <button disabled={busy} onClick={() => onAdvance(it, "implemented")} className="btn-secondary btn-sm">
              Passer en mise en œuvre
            </button>
          )}
          {it.status === "implemented" && m?.baseline_frozen && (
            <button disabled={busy} onClick={() => onMeasure(it)} className="btn-secondary btn-sm"
              title="Le résultat est classé par la mesure, jamais déclaré d'un clic">
              {busy ? "Mesure en cours…" : "Mesurer le résultat"}
            </button>
          )}
          {/* Une action mesurée : nouvelle échéance (même protocole), ajuster, clore. */}
          {it.status === "measured" && (
            <>
              <button disabled={busy} onClick={() => onMeasure(it)} className="btn-secondary btn-sm"
                title="Nouvelle échéance dans le MÊME protocole (baseline et témoins inchangés)">
                {busy ? "Mesure en cours…" : "Nouvelle mesure"}
              </button>
              {run?.result === "objectif_non_atteint" && (
                <Link href="/conversations" className="btn-secondary btn-sm">Ajuster l'action</Link>
              )}
              <button disabled={busy} onClick={() => onAdvance(it, "closed")} className="btn-ghost btn-sm text-ink-tertiary">
                Clore le suivi
              </button>
            </>
          )}
          {/* Pas de protocole mesurable pour cette action (audit, prévision…) :
              on ne fabrique pas de chiffre — l'écoulement du temps n'y changera rien. */}
          {it.status === "implemented" && it.measurement && !m?.baseline_frozen && (
            <span className="meta">Mesure non disponible · historique pré-action insuffisant.</span>
          )}
          {(it.status === "retained" || it.status === "implemented") && (
            <button disabled={busy} onClick={() => onAdvance(it, "abandoned")} className="btn-ghost btn-sm text-ink-tertiary">
              Abandonner
            </button>
          )}
        </div>
      )}
    </div>
  );
}
