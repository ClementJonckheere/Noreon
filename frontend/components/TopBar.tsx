"use client";

import Link from "next/link";
import Icon from "@/components/ui/Icon";

// Barre supérieure : fil d'ariane / sélecteur d'espace à gauche, état de
// fraîcheur des données + notifications à droite. Le sélecteur d'espace est le
// geste qui redéfinit tout le reste de l'écran.
export default function TopBar({
  crumbs = [],
  freshness = "Données à jour",
  notifications = 0,
}: {
  crumbs?: { label: string; href?: string }[];
  freshness?: string;
  notifications?: number;
}) {
  const now = new Date();
  const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  return (
    <header className="h-[60px] shrink-0 flex items-center justify-between px-6 border-b border-line-subtle bg-bg-primary">
      <nav className="flex items-center gap-2 min-w-0 text-[12px] text-ink-tertiary">
        <Link href="/spaces" className="flex items-center gap-1.5 hover:text-ink-primary transition-colors">
          <Icon name="spaces" className="w-4 h-4" />
          <span>Espace de travail</span>
          <Icon name="chevronDown" className="w-3.5 h-3.5" />
        </Link>
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-2 min-w-0">
            <span className="text-line-strong">/</span>
            {c.href ? (
              <Link href={c.href} className="truncate hover:text-ink-primary transition-colors">
                {c.label}
              </Link>
            ) : (
              <span className="truncate text-ink-primary font-medium">{c.label}</span>
            )}
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-4 shrink-0">
        <span className="text-label uppercase text-ink-tertiary hidden sm:flex items-center gap-2">
          {freshness}
          <span className="text-line-strong">·</span>
          <span className="meta">{hhmm}</span>
        </span>
        <button
          type="button"
          aria-label="Notifications"
          className="relative grid place-items-center w-9 h-9 rounded-button text-ink-secondary hover:bg-bg-secondary transition-colors"
        >
          <Icon name="bell" className="w-[18px] h-[18px]" />
          {notifications > 0 && (
            <span className="absolute -top-0.5 -right-0.5 grid place-items-center min-w-[16px] h-4 px-1 rounded-full bg-brand-600 text-white font-mono text-[9px] leading-none">
              {notifications}
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
