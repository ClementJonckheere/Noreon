"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ConceptOverview, ConceptStatus } from "@/lib/api";

// Concepts — le vocabulaire partagé et ses désaccords. On distingue clairement
// quatre états : validé (une définition en vigueur), proposé (Noreon suggère),
// en arbitrage (plusieurs définitions plausibles → décision humaine), et
// « sans source » — qui est une ABSENCE DE DONNÉE, jamais une ambiguïté.
const STATUS: Record<ConceptStatus, { label: string; cls: string; hint: string }> = {
  validated: { label: "Validé", cls: "text-ink-secondary bg-bg-secondary border-line-subtle",
               hint: "Une définition en vigueur." },
  proposed: { label: "Proposé", cls: "text-brand-700 bg-brand-50 border-brand-200",
              hint: "Noreon propose une définition — à valider." },
  needs_arbitration: { label: "En arbitrage", cls: "text-warning-hover bg-warning-bg border-warning-border",
                       hint: "Plusieurs définitions plausibles — un choix vous revient." },
  sans_source: { label: "Sans source", cls: "text-ink-tertiary bg-bg-secondary border-line-subtle",
                 hint: "Aucune donnée ne l'alimente encore." },
};
const ORDER: ConceptStatus[] = ["needs_arbitration", "proposed", "validated", "sans_source"];

export default function ConceptsPage() {
  const [concepts, setConcepts] = useState<ConceptOverview[] | null>(null);
  useEffect(() => { api.conceptsOverview().then(setConcepts).catch(() => setConcepts([])); }, []);

  const groups = ORDER
    .map((s) => [s, (concepts ?? []).filter((c) => c.status === s)] as const)
    .filter(([, list]) => list.length > 0);

  return (
    <div className="space-y-6 fade-in">
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">Concepts</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Le vocabulaire partagé. Une seule définition en vigueur à la fois par concept ;
          c'est ce qui traduit les données brutes en langage métier dans les réponses.
        </p>
      </header>

      {concepts === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : concepts.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucun concept encore</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Les concepts émergent d'une source profilée : Noreon propose, vous validez.
          </p>
          <div className="pt-2"><Link href="/data" className="btn-secondary">Connecter une source</Link></div>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map(([status, list]) => (
            <section key={status} className="space-y-2.5">
              <h2 className="text-label uppercase text-ink-tertiary">
                {STATUS[status].label} ({list.length})
              </h2>
              {list.map((c) => (
                <ConceptCard key={c.id} c={c} />
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function ConceptCard({ c }: { c: ConceptOverview }) {
  const st = STATUS[c.status];
  const arbitrable = c.status === "needs_arbitration";
  const inner = (
    <div className={`card p-4 flex items-start justify-between gap-3 ${arbitrable ? "hover:border-line-strong transition-colors" : ""}`}>
      <div className="min-w-0 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="text-subhead text-ink-primary truncate">{c.name}</span>
          <span className={`tag border shrink-0 ${st.cls}`}>{st.label}</span>
        </div>
        {c.description && <div className="text-body text-ink-secondary truncate">{c.description}</div>}
        <div className="meta">
          {c.reference_label
            ? <>En vigueur : définition « {c.reference_label} » · v{c.reference_version} · </>
            : null}
          {c.definition_count > 0
            ? `${c.definition_count} définition${c.definition_count > 1 ? "s" : ""}`
            : st.hint}
        </div>
      </div>
      {arbitrable && <span className="btn-secondary btn-sm shrink-0">Arbitrer →</span>}
    </div>
  );
  return arbitrable ? <Link href={`/concepts/${c.id}`}>{inner}</Link> : inner;
}
