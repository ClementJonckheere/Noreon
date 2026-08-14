"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Connection, QualityScore } from "@/lib/api";
import { useSession } from "@/lib/session";
import SubNav from "@/components/SubNav";

// Qualité — page de SURVEILLANCE : l'utilisateur comprend l'état de chaque source
// avant même de l'ouvrir (réserves ouvertes, dernier contrôle), pas un annuaire.
export default function QualityPage() {
  const [conns, setConns] = useState<Connection[] | null>(null);
  const { caps } = useSession();
  useEffect(() => { api.listConnections().then(setConns).catch(() => setConns([])); }, []);
  const sourceCta = caps.manageSources
    ? { href: "/data", label: "Connecter une source" }
    : { href: "/data", label: "Demander une connexion" };

  return (
    <div className="space-y-6 fade-in">
      <SubNav />
      <header className="space-y-1">
        <h1 className="text-title text-ink-primary">Qualité</h1>
        <p className="text-body text-ink-secondary max-w-reading">
          Jusqu'où Noreon peut se fier aux données — les contrôles qui tournent avant
          chaque réponse, pas un score global opaque.
        </p>
      </header>

      {conns === null ? (
        <div className="text-body text-ink-tertiary">Chargement…</div>
      ) : conns.length === 0 ? (
        <div className="card p-8 text-center space-y-2">
          <div className="text-subhead text-ink-primary">Aucune source à contrôler</div>
          <p className="text-body text-ink-tertiary max-w-reading mx-auto">
            Connectez une source à cet espace pour que Noreon puisse vérifier sa fraîcheur,
            sa complétude et sa cohérence. Aucune donnée n'est pas la même chose qu'aucun
            problème détecté.
          </p>
          <div className="pt-2"><Link href={sourceCta.href} className="btn-secondary">{sourceCta.label}</Link></div>
        </div>
      ) : (
        <div className="space-y-2.5">
          {conns.map((c) => <SourceRow key={c.id} c={c} />)}
        </div>
      )}
    </div>
  );
}

const CONFORM = 0.9;
const DIM_ORDER = ["Fraîcheur", "Complétude", "Cohérence", "Validité", "Unicité"];

function SourceRow({ c }: { c: Connection }) {
  const [scores, setScores] = useState<QualityScore[] | null>(null);
  useEffect(() => { api.quality(c.id).then(setScores).catch(() => setScores([])); }, [c.id]);

  const status = deriveStatus(scores);

  return (
    <Link href={`/quality/${c.id}`} className="card p-4 flex items-center justify-between gap-4 hover:border-line-strong transition-colors">
      <div className="min-w-0">
        <div className="text-subhead text-ink-primary truncate">{c.name}</div>
        <div className="meta mt-0.5">{c.engine}</div>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        {status && (
          <div className="text-right hidden sm:block">
            <div className={`text-small flex items-center gap-1.5 justify-end ${status.cls}`}>
              <span className={`w-2 h-2 rounded-full ${status.dot}`} />{status.label}
            </div>
            {status.sub && <div className="meta">{status.sub}</div>}
          </div>
        )}
        <span className="btn-secondary btn-sm">Voir les contrôles →</span>
      </div>
    </Link>
  );
}

function deriveStatus(scores: QualityScore[] | null) {
  if (scores === null) return { cls: "text-ink-tertiary", dot: "bg-line-strong", label: "…", sub: "" };
  const cols = scores.filter((s) => s.level === "column");
  if (!cols.length) return { cls: "text-ink-tertiary", dot: "bg-line-strong", label: "Non contrôlée", sub: "Aucun contrôle n'a encore tourné" };

  const agg: Record<string, { sum: number; n: number }> = {};
  let latest = 0;
  for (const c of cols) {
    if (c.computed_at) latest = Math.max(latest, Date.parse(c.computed_at));
    for (const d of c.dimensions ?? []) {
      if (!d.applicable || d.score == null) continue;
      const a = (agg[d.name] ??= { sum: 0, n: 0 });
      a.sum += d.score; a.n += 1;
    }
  }
  const weak = DIM_ORDER.filter((n) => agg[n]?.n && agg[n].sum / agg[n].n < CONFORM);
  const controlled = latest ? `Contrôlé ${ago(latest)}` : "";
  if (weak.length === 0) {
    return { cls: "text-success", dot: "bg-success", label: "Tous les contrôles conformes", sub: controlled };
  }
  return { cls: "text-warning-hover", dot: "bg-warning", label: `${weak[0]} à surveiller`, sub: `${weak.length} réserve${weak.length > 1 ? "s" : ""} ouverte${weak.length > 1 ? "s" : ""} · ${controlled}` };
}

function ago(ms: number): string {
  const m = Math.max(0, Math.round((Date.now() - ms) / 60000));
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.round(h / 24)} j`;
}
