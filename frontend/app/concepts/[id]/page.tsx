"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ArbitrationPreview, ConceptDefinitionView, ConceptDetail } from "@/lib/api";
import { useCurrentSpace } from "@/lib/space";

// Arbitrage d'un concept — la vraie valeur de Noreon : voir l'IMPACT avant de
// trancher. On choisit une définition, on visualise sa population (calculée sur une
// source datée) et ce que le changement engage, PUIS on choisit la référence.
// Un impact obsolète bloque la décision tant qu'il n'est pas recalculé.
const num = (x: number | null) => (x == null ? "—" : Math.round(x).toLocaleString("fr-FR").replace(/ |,/g, " "));

function ago(iso: string | null): string {
  if (!iso) return "jamais calculé";
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return "calculé il y a moins d'une heure";
  if (h < 48) return `calculé il y a ${Math.round(h)} h`;
  return `calculé il y a ${Math.round(h / 24)} j`;
}

export default function ConceptArbitrationPage() {
  const id = Number(useParams().id);
  const router = useRouter();
  const { space } = useCurrentSpace();
  const [c, setC] = useState<ConceptDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [preview, setPreview] = useState<ArbitrationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  function load() { api.conceptDetail(id, space?.id ?? null).then(setC).catch(() => setErr("Concept introuvable.")); }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id, space?.id]);

  async function choose(defId: number) {
    setSel(defId); setPreview(null); setMsg(null);
    setPreview(await api.conceptArbitrationPreview(id, defId, space?.id ?? null).catch(() => null));
  }
  async function recompute(defId: number) {
    setBusy(true); setMsg(null);
    try { await api.conceptRecomputeImpact(id, defId); load(); await choose(defId); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (sel == null) return;
    setBusy(true); setMsg(null);
    try { await api.conceptArbitrate(id, sel, space?.id ?? null); router.push("/concepts"); }
    catch (e) { setMsg(e instanceof Error ? e.message : "Échec de l'arbitrage."); }
    finally { setBusy(false); }
  }

  if (err) return <div className="space-y-3"><Link href="/concepts" className="text-small text-ink-tertiary hover:text-ink-primary">← Concepts</Link><div className="card p-6 text-body text-ink-secondary">{err}</div></div>;
  if (!c) return <div className="text-body text-ink-tertiary">Chargement…</div>;

  const current = c.definitions.find((d) => d.is_reference) ?? null;
  const chosen = preview?.options.find((o) => o.id === sel) ?? null;

  return (
    <div className="space-y-6 fade-in max-w-3xl">
      <div className="space-y-1">
        <nav className="text-small text-ink-tertiary">
          <Link href="/concepts" className="hover:text-ink-primary">Concepts</Link>
          <span className="mx-1.5">/</span><span className="text-ink-secondary">Arbitrage</span>
        </nav>
        <h1 className="text-title text-ink-primary">{c.name}</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Plusieurs définitions plausibles ont été détectées. Choisissez celle qui fera
          référence — vous voyez son impact, calculé sur une source datée, avant de valider.
        </p>
      </div>

      {current && (
        <div className="card p-4 space-y-1">
          <div className="text-label uppercase text-ink-tertiary">Définition en vigueur</div>
          <div className="text-body text-ink-primary">« {current.label} » · v{current.definition_version}</div>
          <div className="meta">{current.definition_text}</div>
          {current.impact_count != null && (
            <div className="text-small text-ink-secondary">
              <span className="mono text-ink-primary">{num(current.impact_count)}</span> {current.entity_label}
              <span className="text-ink-tertiary"> · {ago(current.evaluated_at)}</span>
            </div>
          )}
        </div>
      )}

      <section className="space-y-2.5">
        <h2 className="text-label uppercase text-ink-tertiary">Choisir la définition de référence</h2>
        {c.definitions.map((d) => (
          <DefinitionOption key={d.id} d={d} selected={sel === d.id}
            busy={busy} onSelect={() => choose(d.id)} onRecompute={() => recompute(d.id)} />
        ))}
      </section>

      {sel != null && preview && chosen && (
        <section className="card p-4 space-y-3">
          <h2 className="text-label uppercase text-ink-tertiary">Ce que ce choix engage</h2>
          <div className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-body">
            <span className="text-ink-secondary">Population de la définition retenue</span>
            <span className="text-right mono text-ink-primary">{num(chosen.impact_count)}</span>
            <span className="text-ink-secondary">Réponses concernées (recalcul)</span>
            <span className="text-right mono text-ink-primary">{preview.propagation.answers_affected}</span>
            <span className="text-ink-secondary">Découvertes à revérifier</span>
            <span className="text-right mono text-ink-primary">{preview.propagation.discoveries_to_recheck}</span>
            <span className="text-ink-secondary">Rapports historiques conservés</span>
            <span className="text-right mono text-ink-primary">
              {preview.propagation.reports_preserved}
              {preview.propagation.preserved_labels.length > 0 &&
                <span className="text-ink-tertiary"> ({preview.propagation.preserved_labels.join(", ")})</span>}
            </span>
          </div>

          {/* Impact obsolète : orange = réserve épistémique, on ne tranche pas dessus. */}
          {chosen.is_stale && (
            <div className="state state-limit">
              <div className="state-body flex items-center justify-between gap-2">
                <span>Les données ont changé depuis ce calcul. Recalculez l'impact avant d'arbitrer.</span>
                <button disabled={busy} onClick={() => recompute(chosen.id)} className="text-brand-700 hover:text-brand-800 underline shrink-0">
                  Recalculer l'impact
                </button>
              </div>
            </div>
          )}
          {msg && <div className="state state-limit"><div className="state-body">{msg}</div></div>}

          <div className="text-small text-ink-tertiary">
            {preview.creates_new_version
              ? <>Créera la définition <span className="text-ink-secondary">v{preview.new_version}</span> du concept.
                  Les rapports déjà validés restent intacts et gardent leur définition d'origine — l'historique est conservé.</>
              : <>Cette définition est déjà la référence en vigueur.</>}
          </div>
          <div className="flex items-center gap-2 pt-0.5">
            <button disabled={busy || !preview.creates_new_version || chosen.is_stale}
              onClick={confirm} className="btn-primary btn-sm">
              {busy ? "Application…" : "Choisir comme définition de référence"}
            </button>
            <button disabled={busy} onClick={() => { setSel(null); setPreview(null); setMsg(null); }} className="btn-ghost btn-sm text-ink-tertiary">
              Annuler
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function DefinitionOption({ d, selected, busy, onSelect, onRecompute }: {
  d: ConceptDefinitionView; selected: boolean; busy: boolean; onSelect: () => void; onRecompute: () => void;
}) {
  return (
    <div className={`card p-4 space-y-1 transition-colors ${selected ? "border-brand-500 ring-1 ring-brand-200" : "hover:border-line-strong"}`}>
      <button type="button" onClick={onSelect} className="w-full text-left">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-body text-ink-primary">« {d.label} »</span>
            {d.is_reference && <span className="tag border text-ink-secondary bg-bg-secondary border-line-subtle shrink-0">en vigueur</span>}
          </div>
          <span className="text-small shrink-0">
            <span className="mono text-ink-primary">{num(d.impact_count)}</span>
            <span className="text-ink-tertiary"> {d.entity_label}</span>
          </span>
        </div>
        <div className="meta text-left">{d.definition_text}</div>
      </button>
      <div className="flex items-center gap-2 text-small">
        <span className={d.is_stale ? "text-warning-hover" : "text-ink-tertiary"}>{ago(d.evaluated_at)}{d.is_stale ? " · à recalculer" : ""}</span>
        <button disabled={busy} onClick={onRecompute} className="text-brand-700 hover:text-brand-800 underline">
          Recalculer l'impact
        </button>
      </div>
    </div>
  );
}
