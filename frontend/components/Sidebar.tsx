"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Icon from "@/components/ui/Icon";
import Kbd from "@/components/ui/Kbd";
import SessionBar from "@/components/SessionBar";
import { Capabilities } from "@/lib/capabilities";
import { useSession } from "@/lib/session";
import { conversationRepository, ConversationSummary } from "@/lib/conversation/repository";

// Sidebar 248 px. La navigation DÉRIVE des capacités. Les dossiers et
// conversations vivent ICI (à gauche), pas dans un second panneau à droite.
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

// Regroupement des conversations par récence (Aujourd'hui / 7 derniers jours / Avant).
function bucket(updatedAt: string | null): "today" | "week" | "older" {
  if (!updatedAt) return "older";
  const d = Date.parse(updatedAt);
  if (isNaN(d)) return "older";
  const days = (Date.now() - d) / 86_400_000;
  if (days < 1) return "today";
  if (days < 7) return "week";
  return "older";
}
const BUCKET_LABEL: Record<string, string> = { today: "Aujourd'hui", week: "7 derniers jours", older: "Plus ancien" };

export default function Sidebar() {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const { caps } = useSession();
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!caps.askQuestions) return;
    const refresh = () => conversationRepository().list().then(setConvs).catch(() => {});
    refresh();
    // Le titre d'une conversation est posé côté serveur après le 1er échange :
    // on rafraîchit la liste (dérive du serveur, jamais d'un état local périmé).
    window.addEventListener("noreon:conversations-changed", refresh);
    return () => window.removeEventListener("noreon:conversations-changed", refresh);
  }, [caps.askQuestions, pathname]);

  if (pathname.startsWith("/login")) return null;

  const isActive = (href: string) =>
    href === "/"
      ? pathname === "/"
      : href === "/data"
      ? pathname.startsWith("/data") || pathname.startsWith("/connections") || pathname.startsWith("/sources")
      : pathname.startsWith(href);

  const items = NAV.filter((i) => !i.cap || caps[i.cap]);
  const activeConvId = pathname.startsWith("/conversations/") ? decodeURIComponent(pathname.split("/")[2] ?? "") : "";

  async function newConversation() {
    if (creating) return;
    setCreating(true);
    try {
      const c = await conversationRepository().create();
      router.push(`/conversations/${c.id}`);
    } catch {
      router.push("/data"); // aucune source : on va connecter des données
    } finally {
      setCreating(false);
    }
  }

  const grouped: Record<string, ConversationSummary[]> = { today: [], week: [], older: [] };
  convs.forEach((c) => grouped[bucket(c.updatedAt)].push(c));

  return (
    <aside className="w-[248px] shrink-0 bg-bg-secondary border-r border-line-subtle flex flex-col">
      <div className="h-[60px] shrink-0 flex items-center gap-2.5 px-[18px] border-b border-line-subtle">
        <span className="grid place-items-center w-[34px] h-[34px] rounded-[8px] bg-ink-primary text-white font-mono text-[15px] leading-none">N</span>
        <span className="text-[17px] font-semibold text-ink-primary tracking-tight">Noreon</span>
      </div>

      <div className="px-3 pt-3">
        <button type="button" className="w-full flex items-center gap-2 h-9 px-3 rounded-[6px] bg-surface-raised border border-line text-ink-tertiary text-[12.5px] hover:border-line-strong transition-colors">
          <Icon name="search" className="w-4 h-4" />
          <span className="flex-1 text-left">Rechercher</span>
          <Kbd />
        </button>
      </div>

      <nav className="px-3 py-3 space-y-0.5 shrink-0">
        {items.map((i) => <NavRow key={i.href} item={i} active={isActive(i.href)} />)}
      </nav>

      {caps.askQuestions && (
        <>
          <div className="px-3 space-y-1.5 shrink-0">
            <button onClick={newConversation} disabled={creating} className="btn-primary w-full !justify-start gap-2 !py-2">
              <Icon name="plus" className="w-4 h-4" /> Nouvelle conversation
            </button>
            <button className="btn-ghost w-full !justify-start gap-2 !py-1.5 text-ink-tertiary">
              <Icon name="folder" className="w-4 h-4" /> Nouveau dossier
            </button>
          </div>

          {/* Dossiers & conversations — à gauche, jamais dans un panneau droit. */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4 min-h-0">
            {(["today", "week", "older"] as const).map((k) =>
              grouped[k].length === 0 ? null : (
                <div key={k}>
                  <div className="px-2 text-label uppercase text-ink-tertiary mb-1">{BUCKET_LABEL[k]}</div>
                  <div className="space-y-0.5">
                    {grouped[k].map((c) => {
                      const active = c.id === activeConvId;
                      return (
                        <Link
                          key={c.id}
                          href={`/conversations/${c.id}`}
                          className={`block rounded-[6px] px-2 py-1.5 text-[12.5px] truncate transition-colors ${
                            active ? "bg-brand-100 text-brand-700 font-medium" : "text-ink-secondary hover:bg-bg-primary"
                          }`}
                          title={c.title}
                        >
                          {c.title}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ),
            )}
          </div>
        </>
      )}

      {!caps.askQuestions && <div className="flex-1" />}

      <div className="border-t border-line-subtle p-3 shrink-0">
        <SessionBar />
      </div>
    </aside>
  );
}
