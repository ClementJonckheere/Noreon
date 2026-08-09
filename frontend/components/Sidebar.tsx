"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/ui/Icon";
import SessionBar from "@/components/SessionBar";

// Sidebar 248 px, fond background-secondary, border-right border-subtle.
// L'identité vient de l'investigation, de la preuve, des décisions et de la
// gouvernance — pas d'une sidebar de template SaaS.
type Item = { href: string; label: string; icon: string; count?: number; dot?: boolean };

const PRIMARY: Item[] = [
  { href: "/", label: "Accueil", icon: "home" },
  { href: "/reports", label: "Rapports", icon: "report" },
  { href: "/sources", label: "Données", icon: "data" },
  { href: "/spaces", label: "Espaces", icon: "spaces" },
  { href: "/metrics", label: "Qualité", icon: "quality" },
];
const SECONDARY: Item[] = [
  { href: "/settings", label: "Contexte métier", icon: "settings" },
  { href: "/users", label: "Gouvernance", icon: "gov" },
];

function NavItem({ item, active }: { item: Item; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-2.5 h-9 pl-[11px] pr-2.5 rounded-[6px] text-[12.5px] transition-colors ${
        active ? "bg-brand-100 text-brand-700 font-medium" : "text-ink-secondary hover:bg-bg-primary"
      }`}
    >
      {/* Pastille 5 px : bleu si actif, gris sinon. */}
      <span
        className={`w-[5px] h-[5px] rounded-full shrink-0 ${active ? "bg-brand-600" : "bg-line-strong"}`}
      />
      <Icon name={item.icon} className="w-[17px] h-[17px] shrink-0" />
      <span className="flex-1 truncate">{item.label}</span>
      {item.count != null && (
        <span className="rounded-[4px] bg-reasoning-subtle px-1.5 py-0.5 font-mono text-[9.5px] font-medium text-reasoning-hover">
          {item.count}
        </span>
      )}
      {item.dot && <span className="w-1.5 h-1.5 rounded-full bg-warning shrink-0" />}
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname() || "/";
  // Surfaces publiques (connexion) : pas de sidebar applicative.
  if (pathname.startsWith("/login")) return null;
  const isActive = (href: string) =>
    href === "/"
      ? pathname === "/"
      : href === "/sources"
      ? pathname.startsWith("/sources") || pathname.startsWith("/connections")
      : pathname.startsWith(href);

  return (
    <aside className="w-[248px] shrink-0 bg-bg-secondary border-r border-line-subtle flex flex-col">
      {/* Entête 60 px : monogramme + logotype. */}
      <div className="h-[60px] flex items-center gap-2.5 px-[18px] border-b border-line-subtle">
        <span className="grid place-items-center w-[34px] h-[34px] rounded-[8px] bg-ink-primary text-white font-mono text-[15px] leading-none">
          N
        </span>
        <span className="text-[17px] font-semibold text-ink-primary tracking-tight">Noreon</span>
      </div>

      {/* Recherche transverse — Ctrl K partout. */}
      <div className="px-3 pt-3">
        <button
          type="button"
          className="w-full flex items-center gap-2 h-9 px-3 rounded-[6px] bg-surface-raised
                     border border-line text-ink-tertiary text-[12.5px] hover:border-line-strong transition-colors"
        >
          <Icon name="search" className="w-4 h-4" />
          <span className="flex-1 text-left">Rechercher</span>
          <span className="kbd">⌘K</span>
        </button>
      </div>

      <nav className="px-3 py-3 space-y-0.5">
        {PRIMARY.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
      </nav>

      {/* Actions de conversation. */}
      <div className="px-3 space-y-1.5">
        <Link href="/" className="btn-primary w-full !justify-start gap-2 !py-2">
          <Icon name="plus" className="w-4 h-4" />
          Nouvelle conversation
        </Link>
      </div>

      <div className="px-3 py-3 mt-1">
        <div className="rule" />
      </div>

      <nav className="px-3 space-y-0.5">
        {SECONDARY.map((i) => (
          <NavItem key={i.href} item={i} active={isActive(i.href)} />
        ))}
      </nav>

      <div className="flex-1" />

      <div className="border-t border-line-subtle p-3">
        <SessionBar />
      </div>
    </aside>
  );
}
