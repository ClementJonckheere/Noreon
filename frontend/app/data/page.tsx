"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Connection, CreateResult } from "@/lib/api";
import PipelineRibbon from "@/components/PipelineRibbon";

const ENGINES = [
  { id: "postgresql", label: "PostgreSQL", kind: "db", port: 5432 },
  { id: "mysql", label: "MySQL / MariaDB", kind: "db", port: 3306 },
  { id: "csv", label: "CSV", kind: "file" },
  { id: "excel", label: "Excel", kind: "file" },
] as const;

const EMPTY = {
  name: "",
  host: "localhost",
  port: 5432,
  database: "",
  username: "",
  password: "",
};

export default function Home() {
  const [conns, setConns] = useState<Connection[]>([]);
  const [engine, setEngine] = useState<string>("postgresql");
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const engineSpec = ENGINES.find((e) => e.id === engine)!;
  const isFile = engineSpec.kind === "file";

  async function load() {
    try {
      setConns(await api.listConnections());
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      let res: CreateResult;
      if (isFile) {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("Sélectionnez un fichier.");
        res = await api.uploadFileConnection(form.name, file);
      } else {
        res = await api.createConnection({
          ...form,
          engine,
          port: Number(form.port) || engineSpec.port,
        });
      }
      setResult(res);
      setForm({ ...EMPTY });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-title text-ink">Données · sources</h1>
        <p className="text-body text-ink-2">
          Ce sur quoi Noreon peut répondre. Chaque source est vérifiée en
          <span className="text-ink font-medium"> lecture seule</span> avant toute analyse.
        </p>
      </header>

      <PipelineRibbon />

      <div className="grid gap-8 md:grid-cols-5">
        <section className="md:col-span-3 space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-heading text-ink">Sources connectées</h2>
            <span className="meta">{conns.length}</span>
          </div>

          {conns.length === 0 && (
            <div className="card p-6 text-body text-ink-3">
              Aucune source pour l'instant. Créez-en une à droite.
            </div>
          )}

          <div className="space-y-2.5">
            {conns.map((c) => (
              <Link
                key={c.id}
                href={`/connections/${c.id}`}
                className="card p-4 flex items-center justify-between hover:border-line-strong transition-colors"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-subhead text-ink truncate">{c.name}</span>
                    <span className="tag tag-neutral">
                      {ENGINES.find((e) => e.id === c.engine)?.label || c.engine}
                    </span>
                  </div>
                  <div className="meta mt-0.5 truncate">
                    {c.engine === "csv" || c.engine === "excel"
                      ? `fichier ${c.engine}`
                      : `${c.username}@${c.host}:${c.port}/${c.database}`}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <ReadOnlyBadge value={c.is_read_only} />
                  <StatusBadge status={c.status} />
                </div>
              </Link>
            ))}
          </div>
        </section>

        <section className="md:col-span-2">
          <div className="card p-5 space-y-4">
            <h2 className="text-subhead text-ink">Nouvelle source</h2>

            <div>
              <label className="field-label">Moteur</label>
              <div className="grid grid-cols-2 gap-2">
                {ENGINES.map((e) => (
                  <button
                    key={e.id}
                    type="button"
                    onClick={() => {
                      setEngine(e.id);
                      if (e.kind === "db") setForm((f) => ({ ...f, port: e.port }));
                    }}
                    className={`btn btn-sm ${
                      engine === e.id
                        ? "bg-brand-600 text-white"
                        : "bg-raised border border-line text-ink-2 hover:border-line-strong"
                    }`}
                  >
                    {e.label}
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={submit} className="space-y-3">
              <Field label="Nom" value={form.name} onChange={(v) => setForm({ ...form, name: v })} required />

              {isFile ? (
                <div>
                  <label className="field-label">
                    Fichier {engine === "excel" ? "(.xlsx)" : "(.csv)"}
                  </label>
                  <input
                    ref={fileRef}
                    type="file"
                    accept={engine === "excel" ? ".xlsx,.xls,.xlsm" : ".csv"}
                    className="field h-auto py-2"
                    required
                  />
                  <p className="text-small text-ink-3 mt-1.5">
                    Le fichier est matérialisé localement en base analytique (lecture seule).
                  </p>
                </div>
              ) : (
                <>
                  <Field label="Hôte" value={form.host} mono onChange={(v) => setForm({ ...form, host: v })} required />
                  <Field label="Port" value={String(form.port)} mono onChange={(v) => setForm({ ...form, port: Number(v) })} />
                  <Field label="Base" value={form.database} mono onChange={(v) => setForm({ ...form, database: v })} required />
                  <Field label="Utilisateur" value={form.username} mono onChange={(v) => setForm({ ...form, username: v })} required />
                  <Field label="Mot de passe" value={form.password} type="password" onChange={(v) => setForm({ ...form, password: v })} />
                </>
              )}

              <button className="btn-primary w-full" disabled={busy}>
                {busy ? "Test en cours…" : isFile ? "Importer & analyser" : "Tester & enregistrer"}
              </button>
            </form>

            {error && (
              <div className="state state-blocker">
                <div className="state-title">Blocage</div>
                <div className="state-body">{error}</div>
              </div>
            )}
            {result && (
              <div className="space-y-2">
                <div className="text-body text-ink">
                  Source « {result.connection.name} » enregistrée.
                </div>
                {result.probe.server_version && (
                  <div className="meta">{result.probe.server_version.split(",")[0]}</div>
                )}
                {result.read_only_alert && (
                  <div className="state state-limit">
                    <div className="state-title">Limite</div>
                    <pre className="state-body whitespace-pre-wrap font-sans">{result.read_only_alert}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  mono,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  mono?: boolean;
  required?: boolean;
}) {
  return (
    <div>
      <label className="field-label">{label}</label>
      <input
        className={`field ${mono ? "mono" : ""}`}
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

// Lecture seule vérifiée = un contrôle technique passé (le seul emploi légitime
// du vert). Un accès en écriture est un blocage : rouge.
function ReadOnlyBadge({ value }: { value: boolean | null }) {
  if (value === true) return <span className="tag tag-success">lecture seule ✓</span>;
  if (value === false) return <span className="tag tag-blocker">écriture ✗</span>;
  return <span className="tag tag-neutral">non testé</span>;
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ok") return <span className="tag tag-success">ok</span>;
  if (status === "error") return <span className="tag tag-blocker">erreur</span>;
  return <span className="tag tag-neutral">non testé</span>;
}
