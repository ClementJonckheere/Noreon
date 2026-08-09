"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import SessionBar from "@/components/SessionBar";

// La navigation ne s'organise pas comme un template SaaS : l'identité vient de
// l'investigation, de la preuve, des décisions et de la gouvernance — pas d'une
// sidebar générique. Deux groupes : le travail courant, puis le socle.
const PRIMARY = [
  { href: "/", label: "Conversations" },
  { href: "/reports", label: "Rapports" },
  { href: "/spaces", label: "Espaces" },
];
const SECONDARY = [
  { href: "/metrics", label: "Qualité & métriques" },
  { href: "/settings", label: "Contexte métier" },
  { href: "/users", label: "Gouvernance" },
];

function NavItem({ href, label, active }: { href: string; label: string; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`flex items-center h-9 px-3 rounded-button text-subhead transition-colors ${
        active
          ? "bg-brand-100 text-brand-800 font-medium"
          : "text-ink-2 hover:bg-paper hover:text-ink"
      }`}
    >
      {label}
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname() || "/";
  // Surfaces publiques (connexion, onboarding) : pas de sidebar applicative.
  if (pathname.startsWith("/login")) return null;
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" || pathname.startsWith("/connections") : pathname.startsWith(href);

  return (
    <aside className="w-[248px] shrink-0 bg-paper-2 border-r border-line flex flex-col">
      {/* Marque — le monogramme identifie Noreon en surface compacte. */}
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line-subtle">
        <span className="grid place-items-center w-8 h-8 rounded-button bg-ink text-white font-mono text-metric leading-none">
          N
        </span>
        <div className="leading-tight">
          <div className="text-subhead font-semibold text-ink tracking-tight">Noreon</div>
          <div className="text-label uppercase text-ink-3">Data Analyst</div>
        </div>
      </div>

      {/* Recherche transverse — un seul champ, appelé par Ctrl K partout. */}
      <div className="px-4 pt-4">
        <button
          type="button"
          className="w-full flex items-center justify-between gap-2 h-9 px-3 rounded-button
                     bg-raised border border-line text-ink-3 text-body hover:border-line-strong transition-colors"
        >
          <span className="truncate">Composer…</span>
          <span className="kbd shrink-0">Ctrl K</span>
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
        {PRIMARY.map((i) => (
          <NavItem key={i.href} {...i} active={isActive(i.href)} />
        ))}
        <div className="rule my-3" />
        {SECONDARY.map((i) => (
          <NavItem key={i.href} {...i} active={isActive(i.href)} />
        ))}
      </nav>

      <div className="border-t border-line-subtle p-4">
        <SessionBar />
      </div>
    </aside>
  );
}
