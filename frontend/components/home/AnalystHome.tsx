"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, Connection, ReportSummary } from "@/lib/api";
import Icon from "@/components/ui/Icon";
import { conversationRepository } from "@/lib/conversation/repository";

// Écran 02 — Accueil analyste (densité équilibrée). Même architecture que 01,
// priorité inversée : « l'analyste voit d'abord ce qui est fragile, pas ce qui
// est nouveau ». La liste de contrôle passe avant les découvertes.

type CheckRow = { count: string; title: string; detail: string; action: string; href: string };

export default function AnalystHome({ name }: { name: string }) {
  const router = useRouter();
  const [conns, setConns] = useState<Connection[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.listConnections().then(setConns).catch(() => {});
    api.reports().then(setReports).catch(() => {});
  }, []);

  async function ask(question?: string) {
    const repo = conversationRepository();
    if (!(await repo.hasSource())) return router.push("/data");
    const qs = question ?? q;
    try {
      const c = await repo.create();
      router.push(`/conversations/${c.id}${qs ? `?q=${encodeURIComponent(qs)}` : ""}`);
    } catch {
      router.push("/data");
    }
  }

  const firstConn = conns[0];
  const cx = (p: string) => (firstConn ? `/connections/${firstConn.id}` : "/data");
  const checklist: CheckRow[] = [
    { count: "2", title: "analyses à vérifier", detail: "Réponses publiées avec une confiance sous 70 %", action: "Ouvrir", href: cx("chat") },
    { count: "3", title: "concepts à valider", detail: "t_clients.a3 · 2 relations inférées", action: "Réviser", href: cx("concepts") },
    { count: "1", title: "donnée fragilise des réponses", detail: "Région manquante sur 4 % des commandes · 3 découvertes concernées", action: "Voir", href: cx("quality") },
    { count: "1", title: "rapport en revue", detail: reports[0]?.title ?? "Revue commerciale T3 · v4, à instruire avant validation", action: "Comparer", href: reports[0] ? `/reports/${reports[0].id}` : "/reports" },
  ];

  return (
    <div className="space-y-7 fade-in density-even">
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">{name ? `Bonjour ${name}` : "Bonjour"}</h1>
        <p className="text-body text-ink-secondary">
          {checklist.length + 3} éléments attendent votre regard.
        </p>
      </header>

      {/* Liste de contrôle : ce qui est fragile d'abord. */}
      <section className="card divide-y divide-line-inset">
        {checklist.map((r, i) => (
          <Link
            key={i}
            href={r.href}
            className="flex items-center gap-3 px-4 py-3 hover:bg-bg-secondary transition-colors group"
          >
            <span className="grid place-items-center w-7 h-7 rounded-[6px] bg-warning-subtle text-warning-hover font-mono text-[13px] font-medium shrink-0">
              {r.count}
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-subhead text-ink-primary">
                {r.count} {r.title}
              </div>
              <div className="text-small text-ink-tertiary truncate">{r.detail}</div>
            </div>
            <span className="btn-secondary btn-sm shrink-0 group-hover:border-line-strong">{r.action}</span>
          </Link>
        ))}
      </section>

      {/* Nouvelles découvertes. */}
      <section className="space-y-2">
        <div className="text-label uppercase text-ink-tertiary">Nouvelles découvertes · 3</div>
        <DiscoveryRow
          title="L'Occitanie devient un second foyer de recul"
          confidence={88}
          onOpen={() => ask("Pourquoi l'Occitanie décroche ?")}
        />
        <DiscoveryRow
          title="Le code promo été n'a produit aucun effet mesurable"
          confidence={79}
          onOpen={() => ask("Le code promo été a-t-il eu un effet ?")}
        />
        <DiscoveryRow
          title="Le panier moyen web progresse pendant que celui des magasins recule"
          confidence={91}
          onOpen={() => ask("Pourquoi le panier moyen web progresse ?")}
        />
      </section>

      {/* Composer une analyse. */}
      <section className="rounded-card border border-line bg-brand-50 p-4 flex items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Composer une analyse…"
          className="flex-1 bg-transparent text-[15px] text-ink-primary placeholder-ink-tertiary focus:outline-none"
        />
        <span className="kbd">⌘K</span>
        <button onClick={() => ask()} className="btn-primary shrink-0">
          <Icon name="plus" className="w-4 h-4" /> Composer
        </button>
      </section>
    </div>
  );
}

function DiscoveryRow({ title, confidence, onOpen }: { title: string; confidence: number; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="w-full card px-4 py-3 flex items-center gap-3 text-left hover:border-line-strong transition-colors"
    >
      <span className="w-[7px] h-[7px] rounded-full bg-reasoning shrink-0" />
      <span className="flex-1 text-body text-ink-primary">{title}</span>
      <span className="metric text-reasoning shrink-0">{confidence} %</span>
    </button>
  );
}
