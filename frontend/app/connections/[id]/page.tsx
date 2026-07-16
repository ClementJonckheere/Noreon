"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  ChatResponse,
  Connection,
  Profile,
  Relation,
  Table,
} from "@/lib/api";

type Tab = "schema" | "profiles" | "chat" | "log";

export default function Workspace() {
  const params = useParams();
  const id = Number(params.id);
  const [conn, setConn] = useState<Connection | null>(null);
  const [tab, setTab] = useState<Tab>("chat");
  const [notice, setNotice] = useState<string | null>(null);

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
            {conn.username}@{conn.host}:{conn.port}/{conn.database}
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={doScan}>
            Scanner le schéma
          </button>
          <button className="btn-ghost" onClick={doProfile}>
            Profiler
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
            ["profiles", "Profils"],
            ["log", "Journal SQL"],
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

      {tab === "chat" && <ChatPanel id={id} />}
      {tab === "schema" && <SchemaPanel id={id} />}
      {tab === "profiles" && <ProfilesPanel id={id} />}
      {tab === "log" && <LogPanel id={id} />}
    </div>
  );
}

/* ------------------------------- CHAT ---------------------------------- */
function ChatPanel({ id }: { id: number }) {
  const [q, setQ] = useState("Combien de clients ?");
  const [busy, setBusy] = useState(false);
  const [resp, setResp] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suggestions = [
    "Combien de clients ?",
    "Quel est le montant moyen des commandes ?",
    "Montre les magasins",
    "top 5 clients par loyalty_points",
  ];

  async function ask(question: string) {
    setBusy(true);
    setError(null);
    try {
      setResp(await api.chat(id, question));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            className="badge bg-white/5 text-noreon-soft hover:text-white"
            onClick={() => {
              setQ(s);
              ask(s);
            }}
          >
            {s}
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
        className="flex gap-2"
      >
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Posez une question en langage naturel…"
        />
        <button className="btn-primary" disabled={busy}>
          {busy ? "…" : "Analyser"}
        </button>
      </form>

      {error && (
        <div className="text-sm text-red-300 bg-red-500/10 rounded-lg p-3">
          {error}
        </div>
      )}
      {resp && <ChatResult r={resp} />}
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
        <div className="card p-4">
          <div className="text-sm">{r.analysis.summary}</div>
          {r.analysis.observations?.length > 0 && (
            <ul className="mt-2 text-xs text-noreon-soft list-disc pl-4">
              {r.analysis.observations.map((o: string, i: number) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {r.confidence && <ConfidenceBar c={r.confidence} />}

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
            <Meta label="Tables utilisées" items={r.tables_used} />
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

/* -------------------------------- LOG ---------------------------------- */
function LogPanel({ id }: { id: number }) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => {
    api.queries(id).then(setRows).catch(() => setRows([]));
  }, [id]);
  if (!rows) return <div className="text-noreon-soft">Chargement…</div>;
  if (rows.length === 0)
    return <div className="text-sm text-noreon-soft">Aucune requête journalisée.</div>;

  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.id} className="card p-3 text-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-noreon-soft">{r.question}</span>
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
