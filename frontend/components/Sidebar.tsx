"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/ui/Icon";
import SessionBar from "@/components/SessionBar";
import { Capabilities } from "@/lib/capabilities";
import { useSession } from "@/lib/session";

// Sidebar 248 px, fond background-secondary. La navigation DÉRIVE des capacités
// (jamais d'un `if (role === …)`). Gouvernance/Journal sortent de la nav ; les
// Espaces passent par le switcher (barre supérieure) ; Concepts et Qualité sont
// des domaines de premier niveau.
type NavItem = { href: string; label: string; icon: string; cap?: keyof Capabilities };

const NAV: NavItem[] = [
  { href: "/", label: "Accueil", icon: "home" },
  { href: "/discoveries", label: "Découvertes", icon: "discoveries", cap: "viewDiscoveries" },
  { href: "/reports", label: "Rapports", icon: "report", cap: "viewReports" },
  { href: "/plan", label: "Plan d'action", icon: "plan", cap: "viewPlan" },
  { href: "/data", label: "Données", icon: "data", cap: "viewData" },
  { href: "/quality", label: "Qualité", icon: "quality", cap: "inspectQuality" },
  { href: "/concepts", label: "Concepts", icon: "concepts", cap: "manageConcepts" },
];

function NavRow({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-2.5 h-9 pl-[11px] pr-2.5 rounded-[6px] text-[12.5px] transition-colors ${
        active ? "bg-brand-100 text-brand-700 font-medium" : "text-ink-secondary hover:bg-bg-primary"
      }`}
    >
      <span className={`w-[5px] h-[5px] rounded-full shrink-0 ${active ? "bg-brand-600" : "bg-line-strong"}`} />
      <Icon name={item.icon} className="w-[17px] h-[17px] shrink-0" />
      <span className="flex-1 truncate">{item.label}</span>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname() || "/";
  const { caps } = useSession();

  if (pathname.startsWith("/login")) return null;

  const isActive = (href: string) =>
    href === "/"
      ? pathname === "/"
      : href === "/data"
      ? pathname.startsWith("/data") || pathname.startsWith("/connections") || pathname.startsWith("/sources")
      : pathname.startsWith(href);

  const items = NAV.filter((i) => !i.cap || caps[i.cap]);

  return (
    <aside className="w-[248px] shrink-0 bg-bg-secondary border-r border-line-subtle flex flex-col">
      {/* Entête 60 px : monogramme + logotype. */}
      <div className="h-[60px] flex items-center gap-2.5 px-[18px] border-b border-line-subtle">
        <span className="grid place-items-center w-[34px] h-[34px] rounded-[8px] bg-ink-primary text-white font-mono text-[15px] leading-none">
          N
        </span>
        <span className="text-[17px] font-semibold text-ink-primary tracking-tight">Noreon</span>
      </div>

      {/* Recherche transverse — ⌘K partout. */}
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
        {items.map((i) => (
          <NavRow key={i.href} item={i} active={isActive(i.href)} />
        ))}
      </nav>

      {/* Actions de conversation (les dossiers/récentes arriveront ici, commit 3). */}
      {caps.askQuestions && (
        <div className="px-3 space-y-1.5">
          <Link href="/" className="btn-primary w-full !justify-start gap-2 !py-2">
            <Icon name="plus" className="w-4 h-4" />
            Nouvelle conversation
          </Link>
        </div>
      )}

      <div className="flex-1" />

      <div className="border-t border-line-subtle p-3">
        <SessionBar />
      </div>
    </aside>
  );
}
