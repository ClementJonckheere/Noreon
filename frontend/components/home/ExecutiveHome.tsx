"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ReportSummary } from "@/lib/api";
import Icon from "@/components/ui/Icon";
import { conversationRepository } from "@/lib/conversation/repository";
import { useCurrentSpace } from "@/lib/space";

// Écran 01 — Accueil dirigeant (densité aérée). « Le dirigeant n'ouvre jamais
// une liste : il ouvre des décisions déjà instruites, avec leur impact estimé
// et le précédent qui les rend crédibles. » Cinq blocs, pas plus.
//
// Les décisions et découvertes du dirigeant proviendront d'une file d'attente
// dédiée (carte des états, objet « File »). En l'attente de cette API globale,
// elles reprennent le récit vitrine du produit (Retail / PACA), tandis que la
// barre de question et le rapport en revue sont câblés sur les vraies routes.

const SUGGESTIONS = [
  "Pourquoi le CA baisse depuis quatre mois ?",
  "Le T3 sera-t-il tenu ?",
  "Où le panier moyen progresse-t-il ?",
];

export default function ExecutiveHome({ name }: { name: string }) {
  const router = useRouter();
  const { mode } = useCurrentSpace();
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.reports().then(setReports).catch(() => {});
  }, []);

  // La question ouvre une CONVERSATION (objet racine) ; la source est résolue
  // par le repository. Sans source, on renvoie vers les données.
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

  const reviewReport = reports[0];

  return (
    <div className="space-y-8 fade-in density-airy">
      <header className="space-y-1">
        <h1 className="text-display text-ink-primary">{name ? `Bonjour ${name}` : "Bonjour"}</h1>
        <p className="text-body text-ink-secondary">Voici ce qui mérite votre attention aujourd'hui.</p>
      </header>

      {/* Barre de question — le point d'entrée décisionnel. */}
      <section className="rounded-card border border-line bg-brand-50 p-4">
        <div className="flex items-center gap-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="Que souhaitez-vous comprendre ?"
            className="flex-1 bg-transparent text-[15px] text-ink-primary placeholder-ink-tertiary focus:outline-none"
          />
          <button onClick={() => ask()} className="btn-primary shrink-0">Analyser</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => ask(s)} className="btn-secondary btn-sm">{s}</button>
          ))}
        </div>
      </section>

      {/* Mode LIVE sans file de décisions : état vide honnête (écran 28) — jamais
          de scénario vitrine mêlé à un environnement réel. */}
      {mode !== "demo" && (
        <>
          {reviewReport ? (
            <section className="space-y-3">
              <div className="text-label uppercase text-ink-tertiary">À instruire</div>
              <Link href={`/reports/${reviewReport.id}`} className="card p-5 flex items-center justify-between hover:border-line-strong transition-colors">
                <div>
                  <div className="text-heading text-ink-primary">{reviewReport.title}</div>
                  <div className="flex items-center gap-1.5 text-body text-warning-hover mt-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-warning" /> Rapport en revue
                  </div>
                </div>
                <span className="btn-secondary">Comparer</span>
              </Link>
            </section>
          ) : (
            <section className="card p-8 text-center space-y-2">
              <div className="text-subhead text-ink-primary">Rien ne requiert votre attention pour l'instant</div>
              <p className="text-body text-ink-tertiary max-w-reading mx-auto">
                Les décisions prioritaires apparaîtront ici dès qu'une analyse aura été
                publiée. Posez une question ci-dessus pour commencer.
              </p>
            </section>
          )}
        </>
      )}

      {/* Décisions prioritaires — scénario vitrine (mode démo uniquement). */}
      {mode === "demo" && (
      <>
      <section className="space-y-3">
        <div className="text-label uppercase text-ink-tertiary">Deux décisions prioritaires</div>

        <DecisionCard
          tag="Impact le plus élevé"
          title="Auditer l'assortiment de Marseille et Nice"
          body="Ces deux magasins portent 71 % du recul de PACA. Douze références High-Tech y ont disparu de l'assortiment en avril sans être remplacées."
          impact="+2 à +5 %"
          precedent="Action comparable · résultat mesuré +3,1 % en mars"
          onAnalyse={() => ask("Pourquoi l'assortiment de Marseille et Nice décroche ?")}
        />
        <DecisionCard
          title="Sécuriser l'approvisionnement High-Tech en Occitanie"
          body="Un second foyer de recul apparaît depuis trois semaines, sur le même motif de rupture."
          impact="+1 à +2 %"
          onAnalyse={() => ask("Pourquoi les ruptures High-Tech augmentent en Occitanie ?")}
        />
      </section>

      {/* Découverte majeure + colonne de suivi. */}
      <section className="grid gap-4 lg:grid-cols-3 items-start">
        <div className="lg:col-span-2 card p-5 space-y-3">
          <div className="flex items-center gap-2">
            <span className="w-[7px] h-[7px] rounded-full bg-reasoning" />
            <span className="text-label uppercase text-reasoning-hover">Découverte majeure</span>
          </div>
          <div className="text-heading text-ink-primary">
            Le panier moyen web progresse pendant que celui des magasins recule
          </div>
          <p className="text-body text-ink-secondary max-w-reading">
            Trois semaines consécutives, sur toutes les régions. Le canal, pas la demande.
          </p>
          <div className="flex gap-8 pt-1">
            <Stat label="Web" value="+6,0 %" />
            <Stat label="Magasin" value="−2,4 %" />
            <Stat label="Confiance" value="91 %" reason />
          </div>
        </div>

        <div className="space-y-4">
          {reviewReport ? (
            <Link href={`/reports/${reviewReport.id}`} className="card p-4 space-y-2 block hover:border-line-strong transition-colors">
              <span className="tag tag-warning">v en revue</span>
              <div className="text-subhead text-ink-primary">{reviewReport.title}</div>
              <div className="flex items-center gap-1.5 text-body text-warning-hover">
                <span className="w-1.5 h-1.5 rounded-full bg-warning" />
                À instruire
              </div>
            </Link>
          ) : (
            <div className="card p-4 space-y-2">
              <span className="tag tag-warning">v4 en revue</span>
              <div className="text-subhead text-ink-primary">Revue commerciale T3</div>
              <div className="flex items-center gap-1.5 text-body text-warning-hover">
                <span className="w-1.5 h-1.5 rounded-full bg-warning" />
                4 écarts depuis la v3 validée
              </div>
              <div className="text-small text-ink-tertiary">Validée le 12 juillet par vous.</div>
            </div>
          )}

          <div className="card p-4 space-y-2">
            <span className="text-label uppercase text-ink-tertiary">Impact mesuré</span>
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[24px] font-medium text-ink-primary">+3,1 %</span>
              <span className="text-small text-ink-tertiary">à 30 jours</span>
            </div>
            <div className="text-small text-ink-secondary">
              Correction des ruptures High-Tech, réseau Sud.
            </div>
            <span className="tag tag-success"><Icon name="check" className="w-3 h-3" /> Contrôlé par Finance</span>
          </div>
        </div>
      </section>
      </>
      )}
    </div>
  );
}

function DecisionCard({
  tag, title, body, impact, precedent, onAnalyse,
}: {
  tag?: string;
  title: string;
  body: string;
  impact: string;
  precedent?: string;
  onAnalyse?: () => void;
}) {
  return (
    <div className="card p-6 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2 min-w-0">
          {tag && <span className="tag tag-brand">{tag}</span>}
          <div className="text-heading text-ink-primary">{title}</div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-label uppercase text-ink-tertiary">Impact estimé</div>
          <div className="font-mono text-[26px] font-medium text-ink-primary leading-tight">{impact}</div>
        </div>
      </div>
      <p className="text-body text-ink-secondary max-w-reading">{body}</p>
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button className="btn-primary">Retenir cette décision</button>
        <button onClick={onAnalyse} className="btn-secondary">Voir l'analyse</button>
        {precedent && (
          <span className="flex items-center gap-1.5 text-small text-ink-tertiary ml-auto">
            <span className="w-1.5 h-1.5 rounded-full bg-success" />
            {precedent}
          </span>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, reason }: { label: string; value: string; reason?: boolean }) {
  return (
    <div>
      <div className="text-label uppercase text-ink-tertiary">{label}</div>
      <div className={`font-mono text-[17px] font-medium ${reason ? "text-reasoning" : "text-ink-primary"}`}>
        {value}
      </div>
    </div>
  );
}
