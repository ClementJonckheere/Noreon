"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { api, Connection, Space } from "@/lib/api";

// Barre supérieure. Fil d'ariane / sélecteur d'espace à gauche ; état de
// FRAÎCHEUR réel + notifications à droite. La fraîcheur dérive de l'état des
// sources — jamais un « à jour » codé en dur : aucune donnée ≠ aucun problème.
type Freshness =
  | { kind: "none" }
  | { kind: "fresh"; at: string }
  | { kind: "watch"; count: number };

export default function TopBar({ crumbs = [] }: { crumbs?: { label: string; href?: string }[] }) {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const [spaces, setSpaces] = useState<Space[] | null>(null);

  useEffect(() => {
    api.listConnections().then(setConns).catch(() => setConns([]));
    api.spaces().then(setSpaces).catch(() => setSpaces([]));
  }, []);

  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

  let fresh: Freshness = { kind: "none" };
  if (conns && conns.length > 0) {
    const watch = conns.filter((c) => c.status === "error").length;
    fresh = watch > 0 ? { kind: "watch", count: watch } : { kind: "fresh", at: hhmm };
  }

  const space = spaces && spaces.length > 0 ? spaces[0] : null;

  return (
    <header className="h-[60px] shrink-0 flex items-center justify-between px-6 border-b border-line-subtle bg-bg-primary">
      <nav className="flex items-center gap-2 min-w-0 text-[12px] text-ink-tertiary">
        <Link href="/spaces" className="flex items-center gap-1.5 hover:text-ink-primary transition-colors">
          <Icon name="spaces" className="w-4 h-4" />
          <span className="text-ink-primary font-medium">{space ? space.name : "Aucun espace"}</span>
          <Icon name="chevronDown" className="w-3.5 h-3.5" />
        </Link>
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-2 min-w-0">
            <span className="text-line-strong">/</span>
            {c.href ? (
              <Link href={c.href} className="truncate hover:text-ink-primary transition-colors">{c.label}</Link>
            ) : (
              <span className="truncate text-ink-primary font-medium">{c.label}</span>
            )}
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-4 shrink-0">
        {fresh.kind === "none" && (
          <span className="text-label uppercase text-ink-tertiary hidden sm:inline">Aucune source connectée</span>
        )}
        {fresh.kind === "fresh" && (
          <span className="text-label uppercase text-ink-tertiary hidden sm:flex items-center gap-2">
            Données à jour <span className="text-line-strong">·</span> <span className="meta">{fresh.at}</span>
          </span>
        )}
        {fresh.kind === "watch" && (
          <span className="text-label uppercase text-warning-hover hidden sm:flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-warning" />
            {fresh.count} source{fresh.count > 1 ? "s" : ""} à surveiller
          </span>
        )}
        <button
          type="button"
          aria-label="Notifications"
          className="relative grid place-items-center w-9 h-9 rounded-button text-ink-secondary hover:bg-bg-secondary transition-colors"
        >
          <Icon name="bell" className="w-[18px] h-[18px]" />
        </button>
      </div>
    </header>
  );
}
