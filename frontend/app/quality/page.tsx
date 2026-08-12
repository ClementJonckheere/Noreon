"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Connection } from "@/lib/api";
import { useSession } from "@/lib/session";

// Qualité — jusqu'où Noreon peut se fier aux données. Domaine de premier niveau
// (pas un enfant de Data). Le drill-down par source montrera fraîcheur,
// complétude, cohérence, stabilité, incidents et conclusions impactées.
export default function QualityPage() {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const { caps } = useSession();
  useEffect(() => { api.listConnections().then(setConns).catch(() => setConns([])); }, []);
  // L'action dérive de la capacité : sans manageSources, on ne « connecte » pas, on demande.
  const sourceCta = caps.manageSources
    ? { href: "/data", label: "Connecter une source" }
    : { href: "/data", label: "Demander une connexion" };

  return (
    <div className="space-y-6 fade-in">
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">Qualité</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Jusqu'où Noreon peut se fier aux données — les contrôles qui tournent avant
          chaque réponse, pas un score global opaque.
        </p>
      </header>

      {conns === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : conns.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucune source à contrôler</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Connectez une source à cet espace pour que Noreon puisse vérifier sa fraîcheur,
            sa complétude et sa cohérence. Aucune donnée n'est pas la même chose qu'aucun
            problème détecté.
          </p>
          <div className="pt-2"><Link href={sourceCta.href} className="btn-secondary">{sourceCta.label}</Link></div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {conns.map((c) => (
            <Link key={c.id} href={`/quality/${c.id}`} className="card p-4 flex items-center justify-between hover:border-line-strong transition-colors">
              <div className="min-w-0">
                <div className="text-subhead text-ink-primary truncate">{c.name}</div>
                <div className="meta mt-0.5 truncate">{c.engine}</div>
              </div>
              <span className="btn-secondary btn-sm shrink-0">Voir la confiance →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
