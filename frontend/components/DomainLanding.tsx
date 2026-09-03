"use client";

import Link from "next/link";

// Un écran vide dit toujours POURQUOI il est vide (principe écran 28). Ces
// domaines de premier niveau seront étoffés dans leur groupe d'écrans ; en
// attendant, une entrée honnête, jamais un vide muet ni des données fictives.
export default function DomainLanding({
  title,
  lead,
  emptyTitle,
  emptyBody,
  cta,
}: {
  title: string;
  lead: string;
  emptyTitle: string;
  emptyBody: string;
  cta?: { href: string; label: string };
}) {
  return (
    <div className="space-y-6 fade-in">
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">{title}</h1>
        <p className="text-body text-ink-secondary max-w-reading">{lead}</p>
      </header>
      <div className="card p-8 text-center space-y-2">
        <div className="text-subhead text-ink-primary">{emptyTitle}</div>
        <p className="text-body text-ink-tertiary max-w-reading mx-auto">{emptyBody}</p>
        {cta && (
          <div className="pt-2">
            <Link href={cta.href} className="btn-secondary">{cta.label}</Link>
          </div>
        )}
      </div>
    </div>
  );
}
