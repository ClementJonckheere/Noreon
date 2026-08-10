"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Connection } from "@/lib/api";
import { useSession } from "@/lib/session";

// Concepts — le vocabulaire commun et ses désaccords (la Semantic Layer).
// Domaine de premier niveau : ce que les données signifient, distinct de ce que
// Noreon connaît (Données) et de la confiance qu'il peut leur accorder (Qualité).
export default function ConceptsPage() {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const { caps } = useSession();
  useEffect(() => { api.listConnections().then(setConns).catch(() => setConns([])); }, []);
  const sourceCta = caps.manageSources
    ? { href: "/data", label: "Connecter une source" }
    : { href: "/data", label: "Demander une connexion" };

  return (
    <div className="space-y-6 fade-in">
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">Concepts</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Le vocabulaire partagé. Une seule définition en vigueur à la fois ; c'est ce
          qui traduit « orders.amount_ttc » en « Chiffre d'affaires » dans les réponses.
        </p>
      </header>

      {conns === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : conns.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucun concept encore</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Les concepts émergent d'une source profilée : Noreon propose, vous validez.
          </p>
          <div className="pt-2"><Link href={sourceCta.href} className="btn-secondary">{sourceCta.label}</Link></div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {conns.map((c) => (
            <Link key={c.id} href={`/connections/${c.id}`} className="card p-4 flex items-center justify-between hover:border-line-strong transition-colors">
              <div className="min-w-0">
                <div className="text-subhead text-ink-primary truncate">{c.name}</div>
                <div className="meta mt-0.5 truncate">{c.engine}</div>
              </div>
              <span className="btn-secondary btn-sm shrink-0">Réviser les concepts</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
