"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { api, Connection, QualityScore, Space } from "@/lib/api";

// Barre supérieure — présente partout, donc PROMESSE implicite : elle ne dit
// jamais « à jour » à la légère. On distingue deux notions trop souvent
// confondues : la CONNEXION synchronisée (technique) et les DONNÉES fraîches
// (contrôle métier). « Données à jour » n'apparaît QUE si la fraîcheur est
// contrôlée et conforme ; sinon « Synchronisé » ou « Fraîcheur à vérifier ».
type Freshness =
  | { kind: "none" }
  | { kind: "synced"; at: string }              // connexion OK, fraîcheur inconnue
  | { kind: "fresh"; at: string }               // fraîcheur contrôlée et conforme
  | { kind: "stale"; count: number }            // fraîcheur en réserve
  | { kind: "watch"; count: number };           // source en erreur

const CONFORM = 0.9;

export default function TopBar({ crumbs = [] }: { crumbs?: { label: string; href?: string }[] }) {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [quality, setQuality] = useState<Record<number, QualityScore[]>>({});

  useEffect(() => {
    api.listConnections().then((cs) => {
      setConns(cs);
      Promise.all(cs.map((c) => api.quality(c.id).then((q) => [c.id, q] as const).catch(() => [c.id, []] as const)))
        .then((entries) => setQuality(Object.fromEntries(entries)));
    }).catch(() => setConns([]));
    api.spaces().then(setSpaces).catch(() => setSpaces([]));
  }, []);

  const fresh = deriveFreshness(conns, quality);
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
        {fresh.kind === "synced" && (
          <span className="text-label uppercase text-ink-tertiary hidden sm:flex items-center gap-2">
            Synchronisé <span className="text-line-strong">·</span> <span className="meta">{fresh.at}</span>
          </span>
        )}
        {fresh.kind === "fresh" && (
          <span className="text-label uppercase text-ink-tertiary hidden sm:flex items-center gap-2">
            Données à jour <span className="text-line-strong">·</span> <span className="meta">{fresh.at}</span>
          </span>
        )}
        {fresh.kind === "stale" && (
          <Link href="/quality" className="text-label uppercase text-warning-hover hidden sm:flex items-center gap-1.5 hover:opacity-80">
            <span className="w-1.5 h-1.5 rounded-full bg-warning" />
            {fresh.count === 1 ? "Fraîcheur à vérifier" : `${fresh.count} sources à surveiller`}
          </Link>
        )}
        {fresh.kind === "watch" && (
          <Link href="/quality" className="text-label uppercase text-warning-hover hidden sm:flex items-center gap-1.5 hover:opacity-80">
            <span className="w-1.5 h-1.5 rounded-full bg-warning" />
            {fresh.count} source{fresh.count > 1 ? "s" : ""} à surveiller
          </Link>
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

function deriveFreshness(conns: Connection[] | null, quality: Record<number, QualityScore[]>): Freshness {
  if (!conns || conns.length === 0) return { kind: "none" };
  const errors = conns.filter((c) => c.status === "error").length;
  if (errors > 0) return { kind: "watch", count: errors };

  let checkedAt = 0;
  let anyEvaluated = false;
  let staleCount = 0;
  for (const c of conns) {
    const cols = (quality[c.id] ?? []).filter((s) => s.level === "column");
    const fresh = cols.flatMap((col) => (col.dimensions ?? [])
      .filter((d) => d.name === "Fraîcheur" && d.applicable && d.score != null)
      .map((d) => d.score as number));
    for (const col of cols) if (col.computed_at) checkedAt = Math.max(checkedAt, Date.parse(col.computed_at));
    if (fresh.length) {
      anyEvaluated = true;
      if (fresh.some((s) => s < CONFORM)) staleCount += 1;
    }
  }
  const at = checkedAt
    ? new Date(checkedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })
    : new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

  if (!anyEvaluated) return { kind: "synced", at };
  if (staleCount > 0) return { kind: "stale", count: staleCount };
  return { kind: "fresh", at };
}
