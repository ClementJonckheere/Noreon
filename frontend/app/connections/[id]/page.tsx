"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AlertsPanel from "@/components/AlertsPanel";
import ChartBlock from "@/components/ChartBlock";
import DefinitionsPanel from "@/components/DefinitionsPanel";
import GraphPanel from "@/components/GraphPanel";
import {
  api,
  API_BASE,
  ChatResponse,
  ConceptMapping,
  Connection,
  Profile,
  QualityScore,
  Relation,
  Table,
  TENANT,
} from "@/lib/api";

type Tab =
  | "schema"
  | "graph"
  | "profiles"
  | "quality"
  | "concepts"
  | "definitions"
  | "alerts"
  | "chat"
  | "log";

export default function Workspace() {
  const params = useParams();
  const id = Number(params.id);
  const [conn, setConn] = useState<Connection | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
  const [notice, setNotice] = useState<string | null>(null);
  // Historique rejouable : question relancée depuis l'onglet Historique.
  const [replay, setReplay] = useState<{ q: string; n: number } | null>(null);

  async function refresh() {
    setConn(await api.getConnection(id));
  }
  useEffect(() => {
    refresh();
  }, [id]);

  async function doScan() {
    setNotice("Scan en cours…");
    try {
      const r = await api.scan(id);
      setNotice(`${r.message} (${r.table_count} tables, v${r.version})`);
      refresh();
    } catch (e: any) {
      setNotice(`Erreur : ${e.message}`);
    }
  }
  async function doProfile() {
    setNotice("Profilage lancé (tâche asynchrone)…");
    try {
      await api.profile(id);
      setTimeout(() => setNotice("Profilage terminé."), 2500);
    } catch (e: any) {
      setNotice(`Erreur : ${e.message}`);
    }
  }
  async function doQuality() {
    setNotice("Calcul du score qualité…");
    try {
      const r = await api.runQuality(id);
      setNotice(`Score qualité calculé : base ${Math.round(r.base_score * 100)}% (${r.columns_scored} colonnes, ${r.relations_scored} relations).`);
    } catch (e: any) {
      setNotice(`Erreur : ${e.message}`);
    }
  }

  if (!conn) return <div className="text-noreon-soft">Chargement…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-xs text-noreon-soft hover:underline">
            ← Connexions
          </Link>
          <h1 className="text-2xl font-semibold">{conn.name}</h1>
          <div className="text-xs text-noreon-soft mono">
            <span className="uppercase mr-2">{conn.engine}</span>
            {conn.engine === "csv" || conn.engine === "excel"
              ? "fichier importé (SQLite local)"
              : `${conn.username}@${conn.host}:${conn.port}/${conn.database}`}
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={doScan}>
            Scanner le schéma
          </button>
          <button className="btn-ghost" onClick={doProfile}>
            Profiler
          </button>
          <button className="btn-ghost" onClick={doQuality}>
            Score qualité
          </button>
        </div>
      </div>

      {conn.is_read_only === false && (
        <div className="text-sm text-amber-200 bg-amber-500/10 rounded-lg p-3">
          Ce compte n’est pas en lecture seule — les analyses sont bloquées tant
          que les droits ne sont pas corrigés.
        </div>
      )}
      {notice && (
        <div className="text-sm text-noreon-soft bg-white/5 rounded-lg p-3">
          {notice}
        </div>
      )}

      <nav className="flex gap-1 border-b border-noreon-border">
        {(
          [
            ["chat", "Chat"],
            ["schema", "Schéma"],
            ["graph", "Graphe"],
            ["profiles", "Profils"],
            ["quality", "Qualité"],
            ["concepts", "Concepts"],
            ["definitions", "Définitions"],
            ["alerts", "Alertes"],
            ["log", "Historique"],
          ] as [Tab, string][]
        ).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${
              tab === t
                ? "border-noreon-accent text-white"
                : "border-transparent text-noreon-soft hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "chat" && (
        <ChatPanel id={id} replay={replay} onNavigate={(t) => setTab(t)} />
      )}
      {tab === "schema" && <SchemaPanel id={id} />}
      {tab === "graph" && <GraphPanel id={id} />}
      {tab === "profiles" && <ProfilesPanel id={id} />}
      {tab === "quality" && <QualityPanel id={id} />}
      {tab === "concepts" && <ConceptsPanel id={id} />}
      {tab === "definitions" && <DefinitionsPanel />}
      {tab === "alerts" && <AlertsPanel id={id} />}
      {tab === "log" && (
        <LogPanel
          id={id}
          onReplay={(q) => {
            setReplay({ q, n: Date.now() });
            setTab("chat");
          }}
        />
      )}
    </div>
  );
}

/* ------------------------------- CHAT ---------------------------------- */
// --- Icônes de ligne (SVG inline, sans dépendance externe) ---
const ICONS: Record<string, JSX.Element> = {
  question: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .8-1 1.7" /><path d="M12 17h.01" /></>,
  report: <><path d="M6 3h9l4 4v14H6z" /><path d="M15 3v4h4" /><path d="M9 12h6M9 16h6" /></>,
  anomaly: <><path d="M4 15l4-5 3 3 4-6 5 7" /><path d="M4 20h16" /></>,
  compare: <><path d="M4 7h7M4 12h7M4 17h7" /><path d="M20 7h-6M20 12h-6M20 17h-6" /></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M3 10h18M9 4v16" /></>,
  hash: <><path d="M5 9h14M5 15h14M10 4l-2 16M16 4l-2 16" /></>,
  bars: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
  pie: <><path d="M12 3a9 9 0 1 0 9 9h-9z" /><path d="M12 3v9h9" /></>,
  shield: <><path d="M12 3l7 3v6c0 5-3.5 7.5-7 9-3.5-1.5-7-4-7-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  warning: <><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17h.01" /></>,
  bell: <><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
  send: <><path d="M12 19V5M5 12l7-7 7 7" /></>,
  attach: <><path d="M21 12l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" /></>,
};

function Icon({ name, className = "w-4 h-4" }: { name: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {ICONS[name]}
    </svg>
  );
}

type Action = {
  label: string;
  icon: string;
  prompt?: string; // pré-remplit la question
  deep?: boolean; // force le mode approfondi
  send?: boolean; // lance directement l'analyse
  tab?: Tab; // ou navigue vers un onglet existant
};

const ACTION_GROUPS: { title: string; actions: Action[] }[] = [
  {
    title: "Analyse",
    actions: [
      { label: "Poser une question", icon: "question" },
      { label: "Rapport détaillé", icon: "report", prompt: "Montant total des commandes par mois", deep: true, send: true },
      { label: "Analyser une anomalie", icon: "anomaly", prompt: "Montant total des commandes par magasin", deep: true, send: true },
      { label: "Comparer par période", icon: "compare", prompt: "Nombre de commandes par mois", send: true },
    ],
  },
  {
    title: "Exploration",
    actions: [
      { label: "Explorer les données", icon: "table", prompt: "Montre les magasins", send: true },
      { label: "Compter", icon: "hash", prompt: "Combien de clients ?", send: true },
      { label: "Classement (Top N)", icon: "bars", prompt: "Top 5 clients par loyalty_points", send: true },
      { label: "Répartition", icon: "pie", prompt: "Nombre de commandes par magasin", deep: true, send: true },
    ],
  },
  {
    title: "Qualité & suivi",
    actions: [
      { label: "Audit qualité", icon: "shield", tab: "quality" },
      { label: "Profils & données manquantes", icon: "clock", tab: "profiles" },
      { label: "Détecter des anomalies", icon: "warning", prompt: "Montant moyen des commandes par magasin", deep: true, send: true },
      { label: "Alertes", icon: "bell", tab: "alerts" },
    ],
  },
];

function ChatPanel({
  id,
  replay,
  onNavigate,
}: {
  id: number;
  replay?: { q: string; n: number } | null;
  onNavigate?: (tab: Tab) => void;
}) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [deep, setDeep] = useState(true); // approfondie (détaille) vs rapide (essentiel)
  const [resp, setResp] = useState<ChatResponse | null>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Historique rejouable : une question relancée depuis l'onglet Historique.
  useEffect(() => {
    if (replay?.q) {
      setQ(replay.q);
      ask(replay.q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay?.n]);

  async function ask(question: string, deepMode: boolean = deep) {
    const text = question.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    setAsked(text);
    try {
      setResp(await api.chat(id, text, deepMode));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function runAction(a: Action) {
    if (a.tab) {
      onNavigate?.(a.tab);
      return;
    }
    if (a.deep !== undefined) setDeep(a.deep);
    if (a.prompt) setQ(a.prompt);
    if (a.prompt && a.send) {
      ask(a.prompt, a.deep ?? deep);
    } else {
      inputRef.current?.focus();
    }
  }

  const started = busy || resp || asked;

  return (
    <div className="space-y-5">
      {/* État initial : lanceur d'actions catégorisées (façon palette). */}
      {!started && (
        <div className="card p-6 space-y-5">
          <div>
            <h2 className="text-lg font-semibold">Chat</h2>
            <p className="text-sm text-noreon-soft">
              Posez une question sur vos données et obtenez une réponse argumentée.
            </p>
          </div>
          {ACTION_GROUPS.map((g) => (
            <div key={g.title} className="space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-noreon-soft">
                {g.title}
              </div>
              <div className="flex flex-wrap gap-2">
                {g.actions.map((a) => (
                  <button
                    key={a.label}
                    type="button"
                    onClick={() => runAction(a)}
                    className="btn-ghost text-slate-200"
                  >
                    <Icon name={a.icon} />
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Composer : zone de saisie multi-lignes + mode + envoi. */}
      <Composer
        q={q}
        setQ={setQ}
        deep={deep}
        setDeep={setDeep}
        busy={busy}
        inputRef={inputRef}
        onSubmit={() => ask(q)}
        onReset={
          started
            ? () => {
                setResp(null);
                setAsked(null);
                setError(null);
                setQ("");
              }
            : undefined
        }
      />

      {error && (
        <div className="text-sm text-red-300 bg-red-500/10 rounded-lg p-3">
          {error}
        </div>
      )}
      {asked && (
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-2xl bg-noreon-accent/20 border border-noreon-accent/30 px-4 py-2 text-sm">
            {asked}
          </div>
        </div>
      )}
      {busy && (
        <div className="text-sm text-noreon-soft flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
          {deep ? "Analyse approfondie en cours (requêtes de suivi)…" : "Analyse en cours…"}
        </div>
      )}
      {resp && <ChatResult r={resp} />}
    </div>
  );
}

function Composer({
  q,
  setQ,
  deep,
  setDeep,
  busy,
  inputRef,
  onSubmit,
  onReset,
}: {
  q: string;
  setQ: (v: string) => void;
  deep: boolean;
  setDeep: (v: boolean) => void;
  busy: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement>;
  onSubmit: () => void;
  onReset?: () => void;
}) {
  return (
    <div className="card p-3 space-y-3">
      {/* Mode de réponse : rapide (essentiel) vs approfondie (analyse métier). */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex rounded-lg border border-noreon-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setDeep(false)}
            className={`px-3 py-1.5 flex items-center gap-1.5 ${
              !deep ? "bg-white/10 text-white" : "text-noreon-soft hover:text-white"
            }`}
          >
            ⚡ Rapide
          </button>
          <button
            type="button"
            onClick={() => setDeep(true)}
            className={`px-3 py-1.5 flex items-center gap-1.5 ${
              deep ? "bg-sky-500/20 text-sky-200" : "text-noreon-soft hover:text-white"
            }`}
          >
            📊 Approfondie
          </button>
        </div>
        <span className="text-xs text-noreon-soft flex-1 min-w-[12rem]">
          {deep
            ? "Détaille : croisements de dimensions, facteurs explicatifs, recommandations."
            : "Essentiel : réponse, graphique et indice de confiance."}
        </span>
        {onReset && (
          <button type="button" onClick={onReset} className="text-xs text-noreon-soft hover:text-white">
            Nouvelle analyse
          </button>
        )}
      </div>

      <div className="relative">
        <textarea
          ref={inputRef}
          rows={2}
          className="input resize-none pr-12"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder="Posez une question en langage naturel…  (Entrée pour envoyer, Maj+Entrée pour un saut de ligne)"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={busy || !q.trim()}
          aria-label="Envoyer"
          className="absolute right-2 bottom-2 w-8 h-8 rounded-full bg-noreon-accent text-white flex items-center justify-center hover:brightness-110 disabled:opacity-40"
        >
          {busy ? "…" : <Icon name="send" />}
        </button>
      </div>
    </div>
  );
}

function ChatResult({ r }: { r: ChatResponse }) {
  const statusColor: Record<string, string> = {
    answered: "text-emerald-300",
    clarification: "text-amber-200",
    blocked: "text-red-300",
    error: "text-red-300",
    no_schema: "text-amber-200",
  };
  return (
    <div className="space-y-4">
      {r.status !== "answered" && (
        <div className={`card p-4 text-sm ${statusColor[r.status] || ""}`}>
          <div className="font-medium capitalize mb-1">{r.status}</div>
          {r.message}
        </div>
      )}

      {r.analysis?.summary && (
        <div className="card p-4 space-y-2">
          <div className="text-sm font-medium">{r.analysis.summary}</div>
          {r.analysis.observations?.length > 0 && (
            <ul className="text-xs text-noreon-soft list-disc pl-4">
              {r.analysis.observations.map((o: string, i: number) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          )}
          {r.analysis.anomalies?.length > 0 && (
            <div className="text-xs bg-amber-500/10 rounded-lg p-2 space-y-1">
              <div className="font-medium text-amber-200">Anomalies détectées</div>
              <ul className="list-disc pl-4 text-amber-200/90">
                {r.analysis.anomalies.map((a: string, i: number) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            </div>
          )}
          {r.analysis.recommendations?.length > 0 && (
            <div className="text-xs space-y-1">
              <div className="font-medium text-sky-300">Recommandations</div>
              <ul className="list-disc pl-4 text-noreon-soft">
                {r.analysis.recommendations.map((rec: string, i: number) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {r.deep && <DeepReport d={r.deep} />}

      {r.privacy && r.privacy.values_protected > 0 && (
        <div className="text-xs text-emerald-300/90 bg-emerald-500/10 rounded-lg px-3 py-2">
          🛡 Privacy Engine — {Object.entries(r.privacy.protected_columns)
            .map(([c, t]) => `${c} (${t})`)
            .join(", ")}{" "}
          : {r.privacy.values_protected} valeur(s) pseudonymisée(s) avant envoi au
          LLM, ré-identifiées localement.
        </div>
      )}

      {r.confidence && <ConfidenceBar c={r.confidence} />}

      {r.chart && r.chart.type !== "table" && r.columns.length > 0 && (
        <ChartBlock columns={r.columns} rows={r.rows} suggestion={r.chart} />
      )}

      {r.columns.length > 0 && (
        <ResultTable columns={r.columns} rows={r.rows} truncated={r.truncated} />
      )}

      {/* Transparence : SQL, tables, colonnes, hypothèses, temps */}
      {r.sql && (
        <details className="card p-4" open>
          <summary className="cursor-pointer text-sm font-medium">
            Transparence de l’analyse
          </summary>
          <div className="mt-3 space-y-3 text-xs">
            <pre className="mono bg-black/40 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">
              {r.sql}
            </pre>
            <div>
              <div className="text-noreon-soft mb-1">Tables utilisées</div>
              <div className="flex flex-wrap gap-1">
                {r.tables_used.map((t) => (
                  <span key={t} className="badge bg-white/5 mono">
                    {t}
                    {r.table_quality?.[t] != null && (
                      <span
                        className={`ml-1 ${
                          r.table_quality[t] >= 90
                            ? "text-emerald-300"
                            : r.table_quality[t] >= 70
                            ? "text-amber-300"
                            : "text-red-300"
                        }`}
                      >
                        · qualité {r.table_quality[t]}%
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
            {r.columns_used.length > 0 && (
              <Meta label="Colonnes utilisées" items={r.columns_used} />
            )}
            {r.assumptions.length > 0 && (
              <div>
                <div className="text-noreon-soft mb-1">Hypothèses retenues</div>
                <ul className="list-disc pl-4 text-amber-200">
                  {r.assumptions.map((a, i) => (
                    <li key={i}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-noreon-soft">
              {r.duration_ms != null && <span>⏱ {r.duration_ms} ms</span>}
              {r.estimated_cost != null && (
                <span>coût estimé {Math.round(r.estimated_cost).toLocaleString()}</span>
              )}
              <span>{r.row_count} ligne(s)</span>
            </div>
            {r.warnings.length > 0 && (
              <div className="text-amber-200">{r.warnings.join(" · ")}</div>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

function DeepReport({ d }: { d: NonNullable<ChatResponse["deep"]> }) {
  const fmt = (n: number) => n.toLocaleString("fr-FR");
  return (
    <details className="card p-4 space-y-3 border border-sky-500/30" open>
      <summary className="cursor-pointer text-sm font-semibold text-sky-300">
        📊 Présentation approfondie — au-delà des chiffres, ce qu'ils veulent dire
      </summary>

      <div className="mt-3 space-y-4">
        {/* Contexte métier */}
        {d.context.length > 0 && (
          <div className="text-xs text-noreon-soft space-y-1">
            {d.context.map((c, i) => (
              <div key={i}>{c}</div>
            ))}
          </div>
        )}

        {/* Facteurs explicatifs (drivers) */}
        {d.drivers.length > 0 && (
          <div className="space-y-1">
            <div className="text-sm font-medium text-sky-200">Facteurs explicatifs</div>
            <ul className="text-xs list-disc pl-4 space-y-1">
              {d.drivers.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Croisement de dimensions */}
        {d.crosstab && d.crosstab.cells.length > 0 && (
          <div className="space-y-1">
            <div className="text-sm font-medium text-sky-200">
              Croisement : {d.crosstab.dim_a} × {d.crosstab.dim_b}
            </div>
            <div className="overflow-x-auto">
              <table className="text-xs w-full">
                <thead className="text-noreon-soft">
                  <tr>
                    <th className="text-left py-1 pr-3">{d.crosstab.dim_a}</th>
                    <th className="text-left py-1 pr-3">{d.crosstab.dim_b}</th>
                    <th className="text-right py-1 pr-3">{d.crosstab.metric}</th>
                    <th className="text-right py-1">effectif</th>
                  </tr>
                </thead>
                <tbody>
                  {d.crosstab.cells.map((c, i) => (
                    <tr key={i} className="border-t border-white/5">
                      <td className="py-1 pr-3">{c.a}</td>
                      <td className="py-1 pr-3">{c.b}</td>
                      <td className="py-1 pr-3 text-right mono">{fmt(c.value)}</td>
                      <td className="py-1 text-right mono text-noreon-soft">{fmt(c.count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Segments par dimension */}
        {d.segments.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium text-sky-200">Segmentation par dimension</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {d.segments.map((s, i) => (
                <div key={i} className="bg-white/5 rounded-lg p-3 space-y-1">
                  <div className="text-xs font-medium">
                    {s.dimension}{" "}
                    <span className="text-noreon-soft">· {s.n_groups} segment(s)</span>
                  </div>
                  {s.groups.map((g, j) => (
                    <div key={j} className="text-xs flex items-center gap-2">
                      <span className="w-24 shrink-0 truncate">{g.segment}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                        <div className="h-full bg-sky-400" style={{ width: `${g.share}%` }} />
                      </div>
                      <span className="mono text-noreon-soft w-10 text-right">{g.share}%</span>
                      {g.avg != null && (
                        <span className="mono text-emerald-300/80 w-16 text-right">
                          ⌀ {fmt(g.avg)}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Points d'attention */}
        {d.findings.length > 0 && (
          <div className="space-y-1">
            <div className="text-sm font-medium text-amber-200">Points d'attention</div>
            <ul className="text-xs list-disc pl-4 space-y-1 text-amber-200/90">
              {d.findings.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Recommandations métier */}
        {d.recommendations.length > 0 && (
          <div className="space-y-1">
            <div className="text-sm font-medium text-emerald-300">Recommandations métier</div>
            <ul className="text-xs list-disc pl-4 space-y-1 text-noreon-soft">
              {d.recommendations.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Transparence : requêtes de suivi exécutées */}
        {d.queries.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-noreon-soft">
              {d.queries.length} requête(s) de suivi (lecture seule, agrégées)
            </summary>
            <div className="mt-2 space-y-2">
              {d.queries.map((q, i) => (
                <pre
                  key={i}
                  className="mono bg-black/40 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap"
                >
                  {q}
                </pre>
              ))}
            </div>
          </details>
        )}
      </div>
    </details>
  );
}

function ConfidenceBar({ c }: { c: { percent: number; factors: string[] } }) {
  const color =
    c.percent >= 80 ? "bg-emerald-400" : c.percent >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between text-sm mb-2">
        <span className="font-medium">Indice de confiance</span>
        <span>{c.percent}%</span>
      </div>
      <div className="h-2 rounded-full bg-white/10 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${c.percent}%` }} />
      </div>
      {c.factors.length > 0 && (
        <ul className="mt-2 text-xs text-noreon-soft list-disc pl-4">
          {c.factors.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Meta({ label, items }: { label: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-noreon-soft mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.map((i) => (
          <span key={i} className="badge bg-white/5 mono">
            {i}
          </span>
        ))}
      </div>
    </div>
  );
}

function ResultTable({
  columns,
  rows,
  truncated,
}: {
  columns: string[];
  rows: any[][];
  truncated: boolean;
}) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-noreon-soft border-b border-noreon-border">
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 mono">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 200).map((row, ri) => (
            <tr key={ri} className="border-b border-noreon-border/50">
              {row.map((v, ci) => (
                <td key={ci} className="px-3 py-1.5 mono">
                  {v === null ? <span className="text-noreon-soft">∅</span> : String(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <div className="px-3 py-2 text-xs text-amber-200">
          Résultats tronqués par le LIMIT automatique.
        </div>
      )}
    </div>
  );
}

/* ------------------------------ SCHEMA --------------------------------- */
function SchemaPanel({ id }: { id: number }) {
  const [tables, setTables] = useState<Table[] | null>(null);
  const [rels, setRels] = useState<Relation[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .schema(id)
      .then(setTables)
      .catch((e) => setErr(e.message));
    api.relations(id).then(setRels).catch(() => {});
  }, [id]);

  if (err)
    return (
      <div className="text-sm text-amber-200 bg-amber-500/10 rounded-lg p-3">
        {err} — lancez un scan.
      </div>
    );
  if (!tables) return <div className="text-noreon-soft">Chargement…</div>;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="lg:col-span-2 space-y-3">
        {tables.map((t) => (
          <div key={t.id} className="card p-4">
            <div className="flex items-center justify-between">
              <div className="font-medium mono">
                {t.schema_name}.{t.table_name}
              </div>
              <span className="badge bg-white/5 text-noreon-soft">
                {t.table_type} · ~{t.estimated_rows ?? "?"} lignes
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {t.columns.map((c) => (
                <span
                  key={c.name}
                  className={`badge mono ${
                    c.is_primary_key
                      ? "bg-noreon-accent/20 text-noreon-accent"
                      : "bg-white/5 text-noreon-soft"
                  }`}
                  title={c.data_type}
                >
                  {c.name}
                  {c.is_primary_key ? " 🔑" : ""}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div>
        <h3 className="text-sm font-medium mb-2">Relations détectées</h3>
        <div className="space-y-2">
          {rels.map((r, i) => (
            <div key={i} className="card p-3 text-xs">
              <div className="mono">
                {r.from_table}.{r.from_column} → {r.to_table}.{r.to_column}
              </div>
              <div className="mt-1 flex gap-2">
                <span
                  className={`badge ${
                    r.kind === "declared"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-amber-500/15 text-amber-200"
                  }`}
                >
                  {r.kind === "declared" ? "FK déclarée" : "FK inférée"}
                </span>
                <span className="text-noreon-soft">
                  confiance {Math.round(r.confidence * 100)}%
                </span>
              </div>
            </div>
          ))}
          {rels.length === 0 && (
            <div className="text-xs text-noreon-soft">Aucune relation.</div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------ PROFILES ------------------------------- */
function ProfilesPanel({ id }: { id: number }) {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  useEffect(() => {
    api.profiles(id).then(setProfiles).catch(() => setProfiles([]));
  }, [id]);

  if (!profiles) return <div className="text-noreon-soft">Chargement…</div>;
  if (profiles.length === 0)
    return (
      <div className="text-sm text-noreon-soft">
        Aucun profil. Cliquez sur « Profiler » (le profilage est asynchrone).
      </div>
    );

  const byTable: Record<string, Profile[]> = {};
  profiles.forEach((p) => {
    (byTable[p.table_name] ||= []).push(p);
  });

  return (
    <div className="space-y-6">
      {Object.entries(byTable).map(([table, cols]) => (
        <div key={table} className="card overflow-x-auto">
          <div className="px-4 py-2 font-medium mono border-b border-noreon-border">
            {table}
          </div>
          <table className="w-full text-xs">
            <thead className="text-noreon-soft text-left">
              <tr>
                {["colonne", "type réel", "PII", "% NULL", "distinct", "min", "max"].map(
                  (h) => (
                    <th key={h} className="px-3 py-2">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {cols.map((p) => (
                <tr key={p.column_name} className="border-t border-noreon-border/40">
                  <td className="px-3 py-1.5 mono">{p.column_name}</td>
                  <td className="px-3 py-1.5">{p.detected_type}</td>
                  <td className="px-3 py-1.5">
                    {p.pii_type ? (
                      <span className="badge bg-red-500/15 text-red-300">{p.pii_type}</span>
                    ) : (
                      ""
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    {p.null_rate == null ? "" : (p.null_rate * 100).toFixed(1)}
                  </td>
                  <td className="px-3 py-1.5">{p.distinct_count}</td>
                  <td className="px-3 py-1.5 mono truncate max-w-[120px]">{p.min_value}</td>
                  <td className="px-3 py-1.5 mono truncate max-w-[120px]">{p.max_value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ QUALITY -------------------------------- */
function scoreColor(pct: number) {
  return pct >= 90 ? "text-emerald-300" : pct >= 70 ? "text-amber-300" : "text-red-300";
}
function barColor(pct: number) {
  return pct >= 90 ? "bg-emerald-400" : pct >= 70 ? "bg-amber-400" : "bg-red-400";
}

function QualityPanel({ id }: { id: number }) {
  const [scores, setScores] = useState<QualityScore[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.quality(id).then(setScores).catch(() => setScores([]));
  }, [id]);

  if (!scores) return <div className="text-noreon-soft">Chargement…</div>;
  if (scores.length === 0)
    return (
      <div className="text-sm text-noreon-soft">
        Aucun score qualité. Cliquez sur « Score qualité » (nécessite un scan et
        un profilage préalables).
      </div>
    );

  const base = scores.find((s) => s.level === "base");
  const tables = scores.filter((s) => s.level === "table");
  const relations = scores.filter((s) => s.level === "relation");
  const columnsByTable: Record<string, QualityScore[]> = {};
  scores
    .filter((s) => s.level === "column")
    .forEach((s) => {
      (columnsByTable[s.table_name!] ||= []).push(s);
    });

  return (
    <div className="space-y-6">
      {base && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="font-medium">Score qualité de la base</span>
            <span className={`text-2xl font-bold ${scoreColor(base.score * 100)}`}>
              {Math.round(base.score * 100)}%
            </span>
          </div>
          <div className="h-2 rounded-full bg-white/10 overflow-hidden">
            <div
              className={`h-full ${barColor(base.score * 100)}`}
              style={{ width: `${base.score * 100}%` }}
            />
          </div>
          <div className="text-xs text-noreon-soft mt-2">{base.detail}</div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-medium">Tables & colonnes</h3>
          {tables.map((t) => {
            const isOpen = open === t.table_name;
            const cols = columnsByTable[t.table_name!] || [];
            return (
              <div key={t.table_name} className="card">
                <button
                  className="w-full flex items-center justify-between p-4"
                  onClick={() => setOpen(isOpen ? null : t.table_name!)}
                >
                  <span className="mono">{t.table_name}</span>
                  <span className={`font-semibold ${scoreColor(t.score * 100)}`}>
                    {Math.round(t.score * 100)}%
                  </span>
                </button>
                {isOpen && (
                  <div className="border-t border-noreon-border divide-y divide-noreon-border/40">
                    {cols.map((c) => (
                      <ColumnQualityRow key={c.column_name} c={c} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div>
          <h3 className="text-sm font-medium mb-2">
            Intégrité des relations
          </h3>
          <div className="space-y-2">
            {relations.map((r) => (
              <div key={r.relation_ref} className="card p-3 text-xs">
                <div className="mono">{r.relation_ref}</div>
                <div className="mt-1 flex items-center gap-2">
                  <span className={`font-semibold ${scoreColor(r.score * 100)}`}>
                    {Math.round(r.score * 100)}%
                  </span>
                  <span className="text-noreon-soft">{r.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ColumnQualityRow({ c }: { c: QualityScore }) {
  return (
    <div className="p-3">
      <div className="flex items-center justify-between">
        <span className="mono text-sm">{c.column_name}</span>
        <span className={`text-sm font-semibold ${scoreColor(c.score * 100)}`}>
          {Math.round(c.score * 100)}%
        </span>
      </div>
      <div className="mt-2 grid gap-1">
        {c.dimensions.map((d) => (
          <div
            key={d.name}
            className={`text-xs flex items-center gap-2 ${
              d.applicable ? "" : "text-noreon-soft/50"
            }`}
          >
            <span className="w-24 shrink-0">{d.name}</span>
            {d.applicable && d.score != null ? (
              <>
                <span className={`w-12 text-right ${scoreColor(d.score * 100)}`}>
                  {Math.round(d.score * 100)}%
                </span>
                <span className="text-noreon-soft">{d.detail}</span>
              </>
            ) : (
              <span className="italic">{d.detail}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------ CONCEPTS ------------------------------- */
const STATUS_LABELS: Record<string, [string, string]> = {
  proposed: ["proposé", "bg-amber-500/15 text-amber-200"],
  validated: ["validé", "bg-emerald-500/15 text-emerald-300"],
  corrected: ["corrigé", "bg-sky-500/15 text-sky-300"],
  rejected: ["rejeté", "bg-red-500/15 text-red-300"],
};

function ConceptsPanel({ id }: { id: number }) {
  const [mappings, setMappings] = useState<ConceptMapping[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<number | null>(null);
  const [correctName, setCorrectName] = useState("");

  async function load() {
    setMappings(await api.semanticList(id).catch(() => []));
  }
  useEffect(() => {
    load();
  }, [id]);

  async function propose() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await api.semanticPropose(id);
      setNotice(
        `${r.proposed} proposition(s), ${r.updated} mise(s) à jour, ` +
          `${r.kept_human_decisions} décision(s) humaine(s) conservée(s), ` +
          `${r.arbitrations_needed} arbitrage(s) requis.`,
      );
      load();
    } catch (e: any) {
      setNotice(`Erreur : ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function review(
    m: ConceptMapping,
    action: "validate" | "reject" | "correct",
    conceptName?: string,
  ) {
    try {
      await api.semanticReview(id, m.id, action, conceptName);
      setCorrecting(null);
      setCorrectName("");
      load();
    } catch (e: any) {
      setNotice(`Erreur : ${e.message}`);
    }
  }

  async function download(format: "csv" | "json") {
    const res = await fetch(api.semanticExportUrl(id, format), {
      headers: { "X-Tenant": TENANT },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dictionnaire_metier.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!mappings) return <div className="text-noreon-soft">Chargement…</div>;

  const proposed = mappings.filter((m) => m.status === "proposed");
  const decided = mappings.filter((m) => m.status !== "proposed");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-primary" onClick={propose} disabled={busy}>
          {busy ? "Analyse…" : "Analyser la sémantique"}
        </button>
        <button className="btn-ghost" onClick={() => download("csv")}>
          Export CSV
        </button>
        <button className="btn-ghost" onClick={() => download("json")}>
          Export JSON
        </button>
        <span className="text-xs text-noreon-soft">
          Noreon propose, vous validez : les corrections enrichissent la mémoire
          entreprise.
        </span>
      </div>

      {notice && (
        <div className="text-sm text-noreon-soft bg-white/5 rounded-lg p-3">{notice}</div>
      )}

      {mappings.length === 0 && (
        <div className="text-sm text-noreon-soft">
          Aucun concept. Lancez « Analyser la sémantique » (nécessite un profilage).
        </div>
      )}

      {proposed.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">À réviser ({proposed.length})</h3>
          {proposed.map((m) => (
            <MappingCard
              key={m.id}
              m={m}
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="btn bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                    onClick={() => review(m, "validate")}
                  >
                    Valider
                  </button>
                  {correcting === m.id ? (
                    <form
                      className="flex gap-1"
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (correctName.trim()) review(m, "correct", correctName.trim());
                      }}
                    >
                      <input
                        autoFocus
                        className="input !w-40 !py-1"
                        placeholder="Bon concept…"
                        value={correctName}
                        onChange={(e) => setCorrectName(e.target.value)}
                      />
                      <button className="btn bg-sky-500/20 text-sky-300">OK</button>
                    </form>
                  ) : (
                    <button
                      className="btn bg-sky-500/20 text-sky-300 hover:bg-sky-500/30"
                      onClick={() => {
                        setCorrecting(m.id);
                        setCorrectName("");
                      }}
                    >
                      Corriger
                    </button>
                  )}
                  <button
                    className="btn bg-red-500/20 text-red-300 hover:bg-red-500/30"
                    onClick={() => review(m, "reject")}
                  >
                    Rejeter
                  </button>
                </div>
              }
            />
          ))}
        </section>
      )}

      {decided.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Dictionnaire ({decided.length})</h3>
          {decided.map((m) => (
            <MappingCard key={m.id} m={m} />
          ))}
        </section>
      )}
    </div>
  );
}

function MappingCard({
  m,
  actions,
}: {
  m: ConceptMapping;
  actions?: React.ReactNode;
}) {
  const [label, cls] = STATUS_LABELS[m.status] || STATUS_LABELS.proposed;
  return (
    <div
      className={`card p-4 space-y-2 ${
        m.needs_arbitration ? "border-amber-500/40" : ""
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="mono text-noreon-soft">
            {m.table_name}.{m.column_name}
          </span>
          <span>→</span>
          <span className="font-medium">{m.concept_name}</span>
          <span className={`badge ${cls}`}>{label}</span>
          <span className="text-xs text-noreon-soft">
            confiance {Math.round(m.confidence * 100)}%
          </span>
        </div>
        {actions}
      </div>
      <div className="text-xs text-noreon-soft">{m.rationale}</div>
      {m.needs_arbitration && m.arbitration_note && (
        <div className="text-xs text-amber-200 bg-amber-500/10 rounded-lg p-2">
          ⚠ Arbitrage requis — {m.arbitration_note}
        </div>
      )}
    </div>
  );
}

/* ----------------------------- HISTORIQUE ------------------------------ */
function LogPanel({
  id,
  onReplay,
}: {
  id: number;
  onReplay?: (question: string) => void;
}) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => {
    api.queries(id).then(setRows).catch(() => setRows([]));
  }, [id]);
  if (!rows) return <div className="text-noreon-soft">Chargement…</div>;
  if (rows.length === 0)
    return <div className="text-sm text-noreon-soft">Aucune analyse dans l'historique.</div>;

  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.id} className="card p-3 text-xs space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-noreon-soft">{r.question}</span>
            <div className="flex items-center gap-2 shrink-0">
              {r.question && onReplay && (
                <button
                  className="btn-ghost !py-0.5 !px-2 text-xs"
                  onClick={() => onReplay(r.question)}
                >
                  ↻ Rejouer
                </button>
              )}
              <span
                className={`badge ${
                  r.status === "ok"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "bg-red-500/15 text-red-300"
                }`}
              >
                {r.status}
              </span>
            </div>
          </div>
          <pre className="mono bg-black/40 rounded p-2 overflow-x-auto whitespace-pre-wrap">
            {r.sql}
          </pre>
          <div className="text-noreon-soft flex gap-3">
            {r.duration_ms != null && <span>⏱ {r.duration_ms} ms</span>}
            {r.row_count != null && <span>{r.row_count} lignes</span>}
            {r.confidence?.percent != null && (
              <span>confiance {r.confidence.percent}%</span>
            )}
            {r.block_reason && <span className="text-red-300">{r.block_reason}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
