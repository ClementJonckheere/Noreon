"use client";

// « Pourquoi ces choix ? » — justifie chaque décision de l'analyse (table,
// colonnes, jointure, graphique). L'explicabilité au premier plan.
export default function WhyChoices({ items }: { items: string[] }) {
  if (!items?.length) return null;
  return (
    <details className="card p-4">
      <summary className="cursor-pointer text-sm font-medium text-indigo-700">
        🧩 Pourquoi ces choix ?
      </summary>
      <ul className="mt-2 text-xs space-y-1 list-disc pl-4 text-slate-600">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </details>
  );
}
