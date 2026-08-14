"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Capabilities } from "@/lib/capabilities";
import { useSession } from "@/lib/session";

// Sous-navigation HORIZONTALE dans la page (jamais un accordéon dans la barre) :
// une destination regroupée expose ses sous-onglets ici. Chaque sous-onglet garde
// sa route, sa capability et son écran — le regroupement est purement de navigation.
// Rien ne s'affiche s'il n'y a qu'un seul sous-onglet accessible.
type Tab = { label: string; href: string; cap: keyof Capabilities; activeOn?: string[] };
const FAMILIES: { match: string[]; tabs: Tab[] }[] = [
  {
    match: ["/data", "/quality", "/connections", "/sources"],
    tabs: [
      { label: "Sources", href: "/data", cap: "viewData", activeOn: ["/data", "/connections", "/sources"] },
      { label: "Qualité", href: "/quality", cap: "inspectQuality", activeOn: ["/quality"] },
    ],
  },
  {
    match: ["/concepts", "/relations"],
    tabs: [
      { label: "Concepts", href: "/concepts", cap: "manageConcepts", activeOn: ["/concepts"] },
      { label: "Relations", href: "/relations", cap: "validateRelation", activeOn: ["/relations"] },
    ],
  },
];

export default function SubNav() {
  const pathname = usePathname() || "";
  const { caps } = useSession();
  const fam = FAMILIES.find((f) => f.match.some((m) => pathname === m || pathname.startsWith(m + "/")));
  if (!fam) return null;
  const tabs = fam.tabs.filter((t) => caps[t.cap]);
  if (tabs.length < 2) return null; // un seul sous-onglet accessible : pas de sous-nav

  const isActive = (t: Tab) =>
    (t.activeOn ?? [t.href]).some((p) => pathname === p || pathname.startsWith(p + "/"));

  return (
    <nav className="flex items-center gap-1 border-b border-line-subtle mb-6" aria-label="Sous-navigation">
      {tabs.map((t) => {
        const active = isActive(t);
        return (
          <Link key={t.href} href={t.href} aria-current={active ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-body transition-colors ${
              active ? "border-brand-600 text-ink-primary font-medium"
                     : "border-transparent text-ink-tertiary hover:text-ink-secondary"}`}>
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
