"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Connection, CreateResult } from "@/lib/api";

const ENGINES = [
  { id: "postgresql", label: "PostgreSQL", kind: "db", port: 5432 },
  { id: "mysql", label: "MySQL / MariaDB", kind: "db", port: 3306 },
  { id: "csv", label: "CSV", kind: "file" },
  { id: "excel", label: "Excel", kind: "file" },
] as const;

const ENGINE_BADGE: Record<string, string> = {
  postgresql: "bg-sky-500/15 text-sky-300",
  mysql: "bg-amber-500/15 text-amber-200",
  csv: "bg-emerald-500/15 text-emerald-300",
  excel: "bg-emerald-500/15 text-emerald-300",
};

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
    <div className="grid gap-8 md:grid-cols-5">
      <section className="md:col-span-3 space-y-4">
        <h1 className="text-2xl font-semibold">Connexions</h1>
        <p className="text-sm text-noreon-soft">
          Sources multi-moteurs : PostgreSQL, MySQL, CSV, Excel. Noreon vérifie
          que l’accès est en <strong>lecture seule</strong> avant toute analyse.
        </p>

        {conns.length === 0 && (
          <div className="card p-6 text-noreon-soft text-sm">
            Aucune connexion pour l’instant. Créez-en une à droite.
          </div>
        )}

        <div className="space-y-3">
          {conns.map((c) => (
            <Link
              key={c.id}
              href={`/connections/${c.id}`}
              className="card p-4 flex items-center justify-between hover:border-noreon-accent transition"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{c.name}</span>
                  <span className={`badge ${ENGINE_BADGE[c.engine] || "bg-white/10"}`}>
                    {ENGINES.find((e) => e.id === c.engine)?.label || c.engine}
                  </span>
                </div>
                <div className="text-xs text-noreon-soft mono">
                  {c.engine === "csv" || c.engine === "excel"
                    ? `fichier ${c.engine}`
                    : `${c.username}@${c.host}:${c.port}/${c.database}`}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <ReadOnlyBadge value={c.is_read_only} />
                <StatusBadge status={c.status} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="md:col-span-2">
        <div className="card p-5 space-y-4">
          <h2 className="font-semibold">Nouvelle connexion</h2>

          <div>
            <label className="text-xs text-noreon-soft">Moteur</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              {ENGINES.map((e) => (
                <button
                  key={e.id}
                  type="button"
                  onClick={() => {
                    setEngine(e.id);
                    if (e.kind === "db") setForm((f) => ({ ...f, port: e.port }));
                  }}
                  className={`btn text-xs justify-center ${
                    engine === e.id
                      ? "bg-noreon-accent text-white"
                      : "border border-noreon-border text-noreon-soft"
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
                <label className="text-xs text-noreon-soft">
                  Fichier {engine === "excel" ? "(.xlsx)" : "(.csv)"}
                </label>
                <input
                  ref={fileRef}
                  type="file"
                  accept={engine === "excel" ? ".xlsx,.xls,.xlsm" : ".csv"}
                  className="input"
                  required
                />
                <p className="text-xs text-noreon-soft mt-1">
                  Le fichier est matérialisé localement en base analytique
                  (lecture seule).
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

            <button className="btn-primary w-full justify-center" disabled={busy}>
              {busy ? "Test en cours…" : isFile ? "Importer & analyser" : "Tester & enregistrer"}
            </button>
          </form>

          {error && (
            <div className="text-sm text-red-300 bg-red-500/10 rounded-lg p-3">{error}</div>
          )}
          {result && (
            <div className="text-sm space-y-2">
              <div className="text-emerald-300">
                Connexion « {result.connection.name} » enregistrée.
              </div>
              {result.probe.server_version && (
                <div className="text-noreon-soft text-xs">
                  {result.probe.server_version.split(",")[0]}
                </div>
              )}
              {result.read_only_alert && (
                <pre className="text-xs text-amber-200 bg-amber-500/10 rounded-lg p-3 whitespace-pre-wrap">
                  {result.read_only_alert}
                </pre>
              )}
            </div>
          )}
        </div>
      </section>
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
      <label className="text-xs text-noreon-soft">{label}</label>
      <input
        className={`input ${mono ? "mono" : ""}`}
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function ReadOnlyBadge({ value }: { value: boolean | null }) {
  if (value === true)
    return <span className="badge bg-emerald-500/15 text-emerald-300">read-only ✓</span>;
  if (value === false)
    return <span className="badge bg-red-500/15 text-red-300">écriture ✗</span>;
  return <span className="badge bg-white/10 text-noreon-soft">non testé</span>;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok: "bg-emerald-500/15 text-emerald-300",
    error: "bg-red-500/15 text-red-300",
    untested: "bg-white/10 text-noreon-soft",
  };
  return <span className={`badge ${map[status] || map.untested}`}>{status}</span>;
}
