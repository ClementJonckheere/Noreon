"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import NotificationBell from "@/components/NotificationBell";
import { api, Connection, QualityScore } from "@/lib/api";
import { useSpaces } from "@/lib/space";

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
  const [quality, setQuality] = useState<Record<number, QualityScore[]>>({});
  const { spaces, current, setCurrent } = useSpaces();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Le compteur « sources à surveiller » reflète l'ESPACE COURANT, jamais tout
  // le tenant : sinon la barre annonce des réserves hors du périmètre visible.
  useEffect(() => {
    api.listConnections(current?.id ?? null).then((cs) => {
      setConns(cs);
      Promise.all(cs.map((c) => api.quality(c.id).then((q) => [c.id, q] as const).catch(() => [c.id, []] as const)))
        .then((entries) => setQuality(Object.fromEntries(entries)));
    }).catch(() => setConns([]));
  }, [current?.id]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const fresh = deriveFreshness(conns, quality);

  return (
    <header className="h-[60px] shrink-0 flex items-center justify-between px-6 border-b border-line-subtle bg-bg-primary">
      <nav className="flex items-center gap-2 min-w-0 text-[12px] text-ink-tertiary">
        {/* Sélecteur d'espace : le nom courant + un badge DÉMO explicite pour un
            espace vitrine — impossible de confondre un espace démo avec un live. */}
        <div className="relative" ref={menuRef}>
          <button type="button" onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 hover:text-ink-primary transition-colors">
            <Icon name="spaces" className="w-4 h-4" />
            <span className="text-ink-primary font-medium">{current ? current.name : "Aucun espace"}</span>
            {current?.mode === "demo" && <span className="tag-demo">DÉMO</span>}
            <Icon name="chevronDown" className="w-3.5 h-3.5" />
          </button>
          {open && spaces.length > 0 && (
            <div className="absolute left-0 top-full mt-1.5 min-w-[220px] z-30 card p-1 shadow-lg">
              {spaces.map((s) => (
                <button key={s.id} type="button"
                  onClick={() => { setCurrent(s.id); setOpen(false); }}
                  className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-button text-left hover:bg-bg-secondary ${s.id === current?.id ? "bg-bg-secondary" : ""}`}>
                  <span className="text-body text-ink-primary truncate">{s.name}</span>
                  {s.mode === "demo" && <span className="tag-demo shrink-0">DÉMO</span>}
                </button>
              ))}
              <Link href="/spaces" onClick={() => setOpen(false)}
                className="block px-2.5 py-1.5 mt-0.5 border-t border-line-inset text-small text-ink-tertiary hover:text-ink-primary">
                Gérer les espaces →
              </Link>
            </div>
          )}
        </div>
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
        <NotificationBell />
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
