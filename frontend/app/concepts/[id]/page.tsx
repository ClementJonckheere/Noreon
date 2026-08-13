"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ArbitrationPreview, ConceptDefinitionView, ConceptDetail } from "@/lib/api";

// Arbitrage d'un concept — la vraie valeur de Noreon : voir l'IMPACT avant de
// trancher. On choisit une définition, on visualise sa population et ce que le
// changement engage (réponses, découvertes, rapports), PUIS on valide. Jamais un
// PATCH aveugle : le preview est calculé côté serveur, sans aucune mutation.
const num = (x: number | null) => (x == null ? "—" : Math.round(x).toLocaleString("fr-FR").replace(/ |,/g, " "));

export default function ConceptArbitrationPage() {
  const id = Number(useParams().id);
  const router = useRouter();
  const [c, setC] = useState<ConceptDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [preview, setPreview] = useState<ArbitrationPreview | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.conceptDetail(id).then(setC).catch(() => setErr("Concept introuvable.")); }, [id]);

  async function choose(defId: number) {
    setSel(defId); setPreview(null);
    setPreview(await api.conceptArbitrationPreview(id, defId).catch(() => null));
  }
  async function confirm() {
    if (sel == null) return;
    setBusy(true);
    try { await api.conceptArbitrate(id, sel); router.push("/concepts"); }
    finally { setBusy(false); }
  }

  if (err) return <div className="space-y-3"><Link href="/concepts" className="text-small text-ink-tertiary hover:text-ink-primary">← Concepts</Link><div className="card p-6 text-body text-ink-secondary">{err}</div></div>;
  if (!c) return <div className="text-body text-ink-tertiary">Chargement…</div>;

  const current = c.definitions.find((d) => d.is_reference) ?? null;

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
          référence — vous voyez son impact avant de valider.
        </p>
      </div>

      {/* Définition en vigueur. */}
      {current && (
        <div className="card p-4 space-y-1">
          <div className="text-label uppercase text-ink-tertiary">Définition en vigueur</div>
          <div className="text-body text-ink-primary">« {current.label} » · v{current.definition_version}</div>
          <div className="meta">{current.definition_text}</div>
          {current.impact_count != null && (
            <div className="text-small text-ink-secondary">
              <span className="mono text-ink-primary">{num(current.impact_count)}</span> {current.entity_label}
            </div>
          )}
        </div>
      )}

      {/* Options candidates — sélection → preview d'impact. */}
      <section className="space-y-2.5">
        <h2 className="text-label uppercase text-ink-tertiary">Choisir la définition de référence</h2>
        {c.definitions.map((d) => (
          <DefinitionOption key={d.id} d={d} selected={sel === d.id} onSelect={() => choose(d.id)} />
        ))}
      </section>

      {/* Impact AVANT décision. */}
      {sel != null && preview && (
        <section className="card p-4 space-y-3">
          <h2 className="text-label uppercase text-ink-tertiary">Ce que ce choix engage</h2>
          <div className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-body">
            <span className="text-ink-secondary">Population de la définition retenue</span>
            <span className="text-right mono text-ink-primary">
              {num(preview.options.find((o) => o.id === sel)?.impact_count ?? null)}
            </span>
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
          {/* Violet = conséquence machine du raisonnement ; orange = réserve. */}
          <div className="rounded-card border border-line-strong bg-bg-secondary p-3 text-small text-ink-secondary">
            {preview.creates_new_version
              ? <>Valider crée la <span className="text-ink-primary font-medium">version v{preview.new_version}</span> du
                  concept. Les rapports déjà validés restent intacts et gardent leur définition d'origine
                  (mention ajoutée) — l'historique est conservé.</>
              : <>Cette définition est déjà la référence en vigueur.</>}
          </div>
          <div className="flex items-center gap-2 pt-0.5">
            <button disabled={busy || !preview.creates_new_version} onClick={confirm} className="btn-primary btn-sm">
              {busy ? "Application…" : `Valider cette définition (v${preview.new_version})`}
            </button>
            <button disabled={busy} onClick={() => { setSel(null); setPreview(null); }} className="btn-ghost btn-sm text-ink-tertiary">
              Annuler
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

function DefinitionOption({ d, selected, onSelect }: {
  d: ConceptDefinitionView; selected: boolean; onSelect: () => void;
}) {
  return (
    <button type="button" onClick={onSelect}
      className={`w-full text-left card p-4 space-y-1 transition-colors ${selected ? "border-brand-500 ring-1 ring-brand-200" : "hover:border-line-strong"}`}>
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
      <div className="meta">{d.definition_text}</div>
    </button>
  );
}
