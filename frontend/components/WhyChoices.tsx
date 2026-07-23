"use client";

import { ChatResponse } from "@/lib/api";

// « Pourquoi ces choix ? » — justifie chaque décision de l'analyse (table,
// colonnes, jointure, graphique). L'explicabilité au premier plan.
//
// La `proof` transforme la justification en PREUVE chiffrée : couverture des
// colonnes nécessaires → score qualité → concept métier validé.
export default function WhyChoices({
  items,
  proof,
}: {
  items: string[];
  proof?: ChatResponse["proof"];
}) {
  if (!items?.length && !proof) return null;
  return (
    <details className="card p-4">
      <summary className="cursor-pointer text-sm font-medium text-indigo-700">
        🧩 Pourquoi ces choix ?
      </summary>

      {proof && (
        <div className="mt-3 rounded-lg border border-indigo-500/25 bg-indigo-500/5 p-3">
          <div className="text-xs font-medium text-indigo-700">
            Preuve — pourquoi la table « {proof.table} » ?
          </div>
          {/* Chaîne de preuve : chaque maillon est un fait vérifiable. */}
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
            {proof.steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-indigo-400">↓</span>}
                <span className="badge bg-white border border-indigo-500/25 text-slate-700">
                  {s}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {items?.length > 0 && (
        <ul className="mt-2 text-xs space-y-1 list-disc pl-4 text-slate-600">
          {items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
      )}
    </details>
  );
}
