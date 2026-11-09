"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, RelationCandidateView, RelationPreview } from "@/lib/api";

// Détail d'une relation candidate — sobre et factuel. On montre les FAITS, le
// candidat alternatif (« pourquoi cette colonne ? »), la fenêtre vérifiée et ce
// que la relation rend possible, AVANT de laisser un humain l'autoriser.
const pct = (x: number | null) => (x == null ? "—" : `${(x * 100).toFixed(1)} %`);
// Cardinalité lisible : « n → 1 » plutôt que « n-1 ».
const CARD: Record<string, string> = { "n-1": "n → 1", "1-1": "1 → 1", "1-n": "1 → n", "n-n": "n ↔ n" };
const card = (c: string | null) => (c ? CARD[c] ?? c : "—");
// Date EXPLICITE pour un élément auditable (jamais « aujourd'hui », illisible dans 6 mois).
function frDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}
const ORIGIN: Record<string, { label: string; hint: string }> = {
  constraint: { label: "Contrainte déclarée", hint: "Une FK/contrainte existe réellement dans la base — la preuve la plus forte." },
  inferred: { label: "Inférée par les valeurs", hint: "Déduite de la couverture et de l'unicité, pas déclarée par la base." },
  declared: { label: "Déclaration utilisateur", hint: "Renseignée par un utilisateur." },
};
function frMonth(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

export default function RelationDetailPage() {
  const id = Number(useParams().id);
  const router = useRouter();
  const [r, setR] = useState<RelationCandidateView | null>(null);
  const [pv, setPv] = useState<RelationPreview | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showExc, setShowExc] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.relationDetail(id).then(setR).catch(() => setErr("Relation introuvable."));
    api.relationPreview(id).then(setPv).catch(() => setPv(null));
  }, [id]);

  async function validate() {
    setBusy(true); setMsg(null);
    try { await api.relationValidate(id); router.push("/relations"); }
    catch (e) { setMsg(e instanceof Error ? e.message : "Échec de la validation."); }
    finally { setBusy(false); }
  }
  async function reject() {
    setBusy(true); setMsg(null);
    try { await api.relationReject(id); router.push("/relations"); }
    finally { setBusy(false); }
  }

  if (err) return <div className="space-y-3"><Link href="/relations" className="text-small text-ink-tertiary hover:text-ink-primary">← Relations</Link><div className="card p-6 text-body text-ink-secondary">{err}</div></div>;
  if (!r) return <div className="text-body text-ink-tertiary">Chargement…</div>;

  const origin = ORIGIN[r.origin] ?? { label: r.origin, hint: "" };
  const validated = r.status === "validated";
  const rejected = r.status === "rejected";
  const alt = r.alternatives[0] ?? null;

  return (
    <div className="space-y-6 fade-in max-w-3xl">
      <div className="space-y-2">
        <nav className="text-small text-ink-tertiary">
          <Link href="/relations" className="hover:text-ink-primary">Relations</Link>
          <span className="mx-1.5">/</span><span className="text-ink-secondary">Relation candidate</span>
        </nav>
        {/* Titre MÉTIER (Semantic Layer) ; lignage physique conservé en preuve, dessous. */}
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-subhead text-ink-primary">{r.left.concept} → {r.right.concept}</h1>
          {validated && <span className="tag border text-ink-secondary bg-bg-secondary border-line-subtle">Validée</span>}
        </div>
        <div className="mono text-small text-ink-tertiary">{r.left.label} → {r.right.label}</div>
      </div>

      {/* FAITS — jamais la seule couverture. */}
      <section className="card p-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
          <Fact k="Couverture" v={pct(r.coverage)} />
          <Fact k="Cardinalité" v={card(r.cardinality)} />
          <Fact k="Unicité cible" v={pct(r.target_uniqueness)} />
          <Fact k="Compatibilité" v={r.type_compatibility ?? "—"} />
          <Fact k="Exceptions" v={String(r.exceptions_count ?? 0)} />
          <Fact k="Fenêtre vérifiée" v={`${frMonth(r.valid_from)} → ${frDate(r.valid_to ?? r.evaluated_at)}`} />
        </div>
        {r.exceptions_note && (
          <div className="meta mt-3 pt-3 border-t border-line-inset">{r.exceptions_note}</div>
        )}
      </section>

      {/* POURQUOI CETTE RELATION ? — candidat retenu vs alternative. */}
      <section className="card p-4 space-y-2">
        <h2 className="text-label uppercase text-ink-tertiary">Pourquoi cette relation ?</h2>
        <p className="text-body text-ink-secondary max-w-reading">
          Cette relation présente la meilleure combinaison de couverture, d'unicité,
          de compatibilité de type et de cardinalité parmi les candidats détectés.
        </p>
        <div className="rounded-card border border-line-subtle divide-y divide-line-inset">
          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <span><span className="text-xs uppercase text-brand-700 mr-2">retenu</span><span className="mono text-ink-primary">{r.right.label}</span></span>
            <span className="mono text-ink-primary">{pct(r.coverage)}</span>
          </div>
          {alt && (
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <span><span className="text-xs uppercase text-ink-tertiary mr-2">suivant</span><span className="mono text-ink-secondary">{alt.table}.{alt.column}</span></span>
              <span className="mono text-ink-tertiary">{pct(alt.coverage)}</span>
            </div>
          )}
        </div>
      </section>

      {/* CE QU'ELLE REND POSSIBLE — dérivé des concepts réels. */}
      {pv && (pv.analyses_possible > 0 || pv.concepts_linkable > 0) && (
        <section className="card p-4 space-y-2">
          <h2 className="text-label uppercase text-ink-tertiary">Ce qu'elle rend possible</h2>
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-body text-ink-secondary">
            <span><span className="mono text-ink-primary">{pv.analyses_possible}</span> croisements analytiques supplémentaires</span>
            <span><span className="mono text-ink-primary">{pv.concepts_linkable}</span> concepts reliables</span>
          </div>
          {pv.examples.length > 0 && (
            <ul className="list-disc pl-4 text-body text-ink-secondary space-y-0.5">
              {pv.examples.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </section>
      )}

      {/* Origine (statut épistémique). */}
      <section className="card p-4 space-y-1">
        <h2 className="text-label uppercase text-ink-tertiary">Origine</h2>
        <div className="text-body text-ink-primary">{origin.label}</div>
        <div className="meta">{origin.hint}</div>
      </section>

      {r.is_stale && (
        <div className="state state-limit"><div className="state-body">Les données ont changé depuis l'évaluation. Recalculez les faits avant de valider.</div></div>
      )}
      {msg && <div className="state state-limit"><div className="state-body">{msg}</div></div>}

      {!validated && !rejected && (
        <div className="flex items-center gap-2">
          <button disabled={busy || r.is_stale} onClick={validate} className="btn-primary btn-sm">
            {busy ? "Validation…" : "Valider cette relation"}
          </button>
          <button disabled={busy} onClick={() => setShowExc((v) => !v)} className="btn-secondary btn-sm">
            Voir les {r.exceptions_count ?? 0} exceptions
          </button>
          <button disabled={busy} onClick={reject} className="btn-ghost btn-sm text-ink-tertiary">Rejeter</button>
        </div>
      )}
      {validated && r.validation_window && (
        <div className="meta">
          Validée{r.validated_by ? ` par ${r.validated_by}` : ""} · fenêtre figée {frMonth(r.validation_window.from)} → {frMonth(r.validation_window.to)}.
        </div>
      )}

      {showExc && (
        <section className="card p-4 space-y-1">
          <h2 className="text-label uppercase text-ink-tertiary">Exceptions ({r.exceptions_count ?? 0})</h2>
          <p className="text-body text-ink-secondary max-w-reading">
            {r.exceptions_note ?? "Valeurs de gauche sans correspondance à droite sur la fenêtre analysée."}
          </p>
          <p className="meta">Le détail ligne à ligne s'ouvrira depuis la Preuve (requête auditable).</p>
        </section>
      )}
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="space-y-0.5">
      <div className="text-label uppercase text-ink-tertiary">{k}</div>
      <div className="mono text-body text-ink-primary">{v}</div>
    </div>
  );
}
