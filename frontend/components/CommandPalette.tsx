"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Icon from "@/components/ui/Icon";
import { useSession } from "@/lib/session";
import { useCurrentSpace } from "@/lib/space";
import { api } from "@/lib/api";
import { conversationRepository } from "@/lib/conversation/repository";

// ⌘K — recherche & commandes universelles. DOMAINE-AGNOSTIQUE : aucune entité
// métier codée en dur. Les catégories (Concepts, Relations, Sources, Rapports)
// sont des PRIMITIVES produit ; leurs libellés viennent des données du tenant.
// Chaque source de résultats est réservée à une CAPACITÉ — on n'interroge un
// endpoint que si l'utilisateur y a droit (il applique lui-même l'autorisation).
// Un accès direct refusé ailleurs reste refusé : ⌘K n'ouvre que ce qui est permis.

type Group = "Aller à" | "Actions" | "Concepts" | "Relations" | "Sources" | "Rapports" | "Conversations";
const GROUP_ORDER: Group[] = ["Actions", "Aller à", "Concepts", "Relations", "Sources", "Rapports", "Conversations"];

type Cmd = {
  id: string;
  group: Group;
  label: string;
  sub?: string;
  icon: string;
  keywords?: string;
  href?: string;
  run?: () => void | Promise<void>;
};

// Normalisation insensible à la casse ET aux accents (recherche en français).
const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{Diacritic}/gu, "");

// Score de pertinence : plus petit = meilleur. -1 = pas de correspondance.
function score(cmd: Cmd, q: string): number {
  if (!q) return 0;
  const hay = norm(`${cmd.label} ${cmd.sub ?? ""} ${cmd.keywords ?? ""}`);
  const label = norm(cmd.label);
  const i = hay.indexOf(q);
  if (i === -1) return -1;
  if (label === q) return 0;
  if (label.startsWith(q)) return 1;
  if (new RegExp(`\\b${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(label)) return 2;
  if (label.includes(q)) return 3;
  return 4; // trouvé dans le sous-titre / mots-clés seulement
}

export default function CommandPalette() {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const { caps } = useSession();
  const { space } = useCurrentSpace();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Index d'entités chargé paresseusement à la 1re ouverture (puis mémoïsé).
  const [entities, setEntities] = useState<Cmd[]>([]);
  const [loaded, setLoaded] = useState(false);

  const close = useCallback(() => { setOpen(false); setQ(""); setIdx(0); }, []);

  // Ouverture : ⌘K / Ctrl+K partout, et le bouton « Rechercher » de la sidebar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("noreon:open-command", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("noreon:open-command", onOpen);
    };
  }, []);

  useEffect(() => { if (open) { setIdx(0); setTimeout(() => inputRef.current?.focus(), 0); } }, [open]);

  // Chargement des entités interrogeables — UNIQUEMENT celles permises par les
  // capacités (l'endpoint concerné applique lui-même l'autorisation).
  useEffect(() => {
    if (!open || loaded) return;
    setLoaded(true);
    const sid = space?.id ?? null;
    const out: Cmd[] = [];
    const jobs: Promise<void>[] = [];
    const push = (c: Cmd) => out.push(c);

    if (caps.arbitrateConcept) jobs.push(
      api.conceptsOverview(sid).then((cs) => cs.forEach((c) =>
        push({ id: `concept-${c.id}`, group: "Concepts", icon: "concepts", label: c.name,
          sub: c.description || undefined, keywords: c.reference_label ?? "",
          // Le détail n'existe que pour un concept en arbitrage ; sinon la liste.
          href: c.status === "needs_arbitration" ? `/concepts/${c.id}` : "/concepts" }))).catch(() => {}));

    if (caps.validateRelation) jobs.push(
      api.relationCandidates(undefined, sid).then((rs) => rs.forEach((r) =>
        push({ id: `relation-${r.id}`, group: "Relations", icon: "relations",
          label: `${r.left.concept} → ${r.right.concept}`,
          sub: `${r.left.label} → ${r.right.label}`, href: `/relations/${r.id}` }))).catch(() => {}));

    if (caps.viewData) jobs.push(
      api.listConnections().then((cs) => cs.forEach((c) =>
        push({ id: `source-${c.id}`, group: "Sources", icon: "data", label: c.name,
          sub: c.engine, keywords: `${c.host ?? ""} ${c.database ?? ""}`, href: `/connections/${c.id}` }))).catch(() => {}));

    if (caps.viewReports) jobs.push(
      api.reports(sid ?? undefined).then((rs) => rs.forEach((r) =>
        push({ id: `report-${r.id}`, group: "Rapports", icon: "report", label: r.title || "Rapport sans titre",
          href: `/reports/${r.id}` }))).catch(() => {}));

    if (caps.askQuestions) jobs.push(
      conversationRepository().list().then((cv) => cv.forEach((c) =>
        push({ id: `conv-${c.id}`, group: "Conversations", icon: "search", label: c.title || "Conversation",
          sub: c.sourceName, href: `/conversations/${c.id}` }))).catch(() => {}));

    Promise.allSettled(jobs).then(() => setEntities(out));
  }, [open, loaded, caps, space?.id]);

  // Navigation & actions — statiques, réservées aux capacités. Miroir de la nav.
  const staticCmds = useMemo<Cmd[]>(() => {
    const c: Cmd[] = [];
    const go = (href: string, label: string, icon: string, cap?: boolean, kw?: string) => {
      if (cap === false) return;
      c.push({ id: `nav-${href}`, group: "Aller à", label, icon, href, keywords: kw });
    };
    if (caps.askQuestions) c.push({
      id: "act-new-conv", group: "Actions", label: "Nouvelle conversation", icon: "plus",
      keywords: "poser question analyse",
      run: async () => { try { const nc = await conversationRepository().create(); router.push(`/conversations/${nc.id}`); } catch { router.push("/data"); } },
    });
    if (caps.manageSources) c.push({
      id: "act-connect", group: "Actions", label: "Connecter une source", icon: "data",
      keywords: "base données postgres mysql csv", href: "/data",
    });
    go("/", "Accueil", "home", true);
    go("/discoveries", "Découvertes", "discoveries", caps.viewDiscoveries);
    go("/reports", "Rapports", "report", caps.viewReports);
    go("/plan", "Plan d'action", "plan", caps.viewPlan);
    go("/data", "Sources de données", "data", caps.viewData, "données");
    go("/quality", "Qualité des données", "quality", caps.inspectQuality, "contrôles");
    go("/concepts", "Concepts", "concepts", caps.arbitrateConcept, "modèle sémantique arbitrage");
    go("/relations", "Relations", "relations", caps.validateRelation, "modèle sémantique");
    return c;
  }, [caps, router]);

  const all = useMemo(() => [...staticCmds, ...entities], [staticCmds, entities]);

  // Filtrage + tri. Requête vide → lanceur (Actions + Aller à uniquement).
  const results = useMemo(() => {
    const nq = norm(q.trim());
    let matched: { cmd: Cmd; s: number }[];
    if (!nq) {
      matched = all.filter((c) => c.group === "Actions" || c.group === "Aller à").map((cmd) => ({ cmd, s: 0 }));
    } else {
      matched = [];
      for (const cmd of all) { const s = score(cmd, nq); if (s >= 0) matched.push({ cmd, s }); }
      matched.sort((a, b) => a.s - b.s);
    }
    // Regroupement en préservant l'ordre des groupes ; plafond par groupe.
    const byGroup = new Map<Group, Cmd[]>();
    for (const { cmd } of matched) {
      const list = byGroup.get(cmd.group) ?? [];
      // Navigation & actions : jamais tronquées ; entités : plafonnées à 6.
      const capMax = cmd.group === "Actions" || cmd.group === "Aller à" ? 20 : 6;
      if (list.length < capMax) { list.push(cmd); byGroup.set(cmd.group, list); }
    }
    const flat: Cmd[] = [];
    const sections: { group: Group; items: Cmd[] }[] = [];
    for (const g of GROUP_ORDER) {
      const items = byGroup.get(g);
      if (items && items.length) { sections.push({ group: g, items }); flat.push(...items); }
    }
    return { sections, flat };
  }, [q, all]);

  useEffect(() => { setIdx((i) => Math.min(i, Math.max(0, results.flat.length - 1))); }, [results.flat.length]);

  const runCmd = useCallback((cmd?: Cmd) => {
    if (!cmd) return;
    close();
    if (cmd.run) cmd.run();
    else if (cmd.href) router.push(cmd.href);
  }, [close, router]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.flat.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); runCmd(results.flat[idx]); }
  }

  if (!open || pathname.startsWith("/login")) return null;

  let running = -1; // index global courant pour le surlignage clavier
  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[12vh] px-4 bg-black/40" onClick={close}>
      <div
        className="w-full max-w-xl bg-bg-primary border border-line-subtle rounded-card shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 h-12 border-b border-line-subtle">
          <Icon name="search" className="w-[18px] h-[18px] text-ink-tertiary shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => { setQ(e.target.value); setIdx(0); }}
            onKeyDown={onKeyDown}
            placeholder="Rechercher un concept, une relation, une source, un rapport…"
            className="flex-1 bg-transparent outline-none text-[14px] text-ink-primary placeholder:text-ink-tertiary"
          />
          <span className="kbd shrink-0">Esc</span>
        </div>

        <div className="max-h-[52vh] overflow-y-auto py-2">
          {results.flat.length === 0 ? (
            <div className="px-4 py-8 text-center text-body text-ink-tertiary">
              {loaded ? "Aucun résultat." : "Chargement…"}
            </div>
          ) : (
            results.sections.map((sec) => (
              <div key={sec.group} className="px-2 pb-1">
                <div className="px-2 pt-2 pb-1 text-[10px] font-medium uppercase tracking-[0.09em] text-ink-tertiary">{sec.group}</div>
                {sec.items.map((cmd) => {
                  running += 1;
                  const active = running === idx;
                  const gi = running;
                  return (
                    <button
                      key={cmd.id}
                      onMouseEnter={() => setIdx(gi)}
                      onClick={() => runCmd(cmd)}
                      className={`w-full flex items-center gap-3 px-2 h-10 rounded-[6px] text-left transition-colors ${
                        active ? "bg-brand-100 text-brand-700" : "text-ink-secondary hover:bg-bg-secondary"
                      }`}
                    >
                      <Icon name={cmd.icon} className="w-[17px] h-[17px] shrink-0" />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] truncate">{cmd.label}</span>
                        {cmd.sub && <span className="block text-[11px] text-ink-tertiary truncate">{cmd.sub}</span>}
                      </span>
                      {active && <span className="kbd shrink-0">↵</span>}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
