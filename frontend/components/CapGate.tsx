"use client";

import Link from "next/link";

// Accès DIRECT à une route sans la capacité requise : on REFUSE (on ne redirige
// jamais silencieusement vers un autre sous-onglet). L'ouverture du premier
// sous-onglet accessible est réservée au clic sur le PARENT (barre latérale).
export default function AccessDenied() {
  return (
    <div className="card p-8 text-center space-y-2 max-w-reading mx-auto mt-6">
      <div className="text-subhead text-ink-primary">Accès restreint</div>
      <p className="text-body text-ink-tertiary">
        Vous n'avez pas l'autorisation d'ouvrir cette section.
      </p>
      <div className="pt-2"><Link href="/" className="btn-secondary">Retour à l'accueil</Link></div>
    </div>
  );
}
