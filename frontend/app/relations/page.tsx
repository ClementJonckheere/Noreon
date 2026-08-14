"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, RelationCandidateView, RelationStatus } from "@/lib/api";
import { useCurrentSpace } from "@/lib/space";
import SubNav from "@/components/SubNav";

// Relations — les liens entre champs, jugés sur des FAITS (couverture, unicité,
// cardinalité, exceptions, fenêtre), pas sur un simple score. Une relation validée
// autorise Noreon à s'en servir ; une FK déclarée par la base a un statut supérieur.
const STATUS: Record<RelationStatus, { label: string; cls: string }> = {
  needs_validation: { label: "À valider", cls: "text-warning-hover bg-warning-bg border-warning-border" },
  candidate: { label: "Candidate", cls: "text-brand-700 bg-brand-50 border-brand-200" },
  validated: { label: "Validée", cls: "text-ink-secondary bg-bg-secondary border-line-subtle" },
  rejected: { label: "Rejetée", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle" },
  archived: { label: "Archivée", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle" },
};
const ORDER: RelationStatus[] = ["needs_validation", "candidate", "validated", "rejected", "archived"];
const ORIGIN: Record<string, string> = { constraint: "Contrainte déclarée", inferred: "Inférée par les valeurs", declared: "Déclaration utilisateur" };
const pct = (x: number | null) => (x == null ? "—" : `${(x * 100).toFixed(1)} %`);

export default function RelationsPage() {
  const { space, ready } = useCurrentSpace();
  const [rels, setRels] = useState<RelationCandidateView[] | null>(null);
  // Cloisonnement PHYSIQUE : seules les relations dont la source est rattachée à
  // l'espace courant sont montrées (un lien physique ne fuit pas d'un périmètre à l'autre).
  useEffect(() => {
    if (!ready) return;
    api.relationCandidates(undefined, space?.id ?? null).then(setRels).catch(() => setRels([]));
  }, [ready, space?.id]);

  const groups = ORDER
    .map((s) => [s, (rels ?? []).filter((r) => r.status === s)] as const)
    .filter(([, list]) => list.length > 0);

  return (
    <div className="space-y-6 fade-in">
      <SubNav />
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">Relations</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Les liens entre champs, jugés sur des faits — couverture, unicité de la cible,
          cardinalité, exceptions, fenêtre vérifiée — et non sur un simple score.
        </p>
      </header>

      {rels === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : rels.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucune relation candidate</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Les relations émergent d'une source profilée : Noreon détecte les liens, vous validez.
          </p>
          <div className="pt-2"><Link href="/data" className="btn-secondary">Connecter une source</Link></div>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map(([status, list]) => (
            <section key={status} className="space-y-2.5">
              <h2 className="text-label uppercase text-ink-tertiary">{STATUS[status].label} ({list.length})</h2>
              {list.map((r) => (
                <Link key={r.id} href={`/relations/${r.id}`}
                  className="card p-4 flex items-start justify-between gap-3 hover:border-line-strong transition-colors">
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="mono text-body text-ink-primary truncate">{r.left.label}</span>
                      <span className="text-ink-tertiary">→</span>
                      <span className="mono text-body text-ink-primary truncate">{r.right.label}</span>
                      <span className={`tag border shrink-0 ${STATUS[status].cls}`}>{STATUS[status].label}</span>
                    </div>
                    <div className="meta">
                      Couverture {pct(r.coverage)} · cardinalité {r.cardinality ?? "—"} ·
                      {" "}{r.exceptions_count ?? 0} exception{(r.exceptions_count ?? 0) > 1 ? "s" : ""} · {ORIGIN[r.origin] ?? r.origin}
                    </div>
                  </div>
                  <span className="btn-secondary btn-sm shrink-0">Examiner →</span>
                </Link>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
