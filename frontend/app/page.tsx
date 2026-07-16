"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Connection, CreateResult } from "@/lib/api";

const EMPTY = {
  name: "",
  host: "localhost",
  port: 5432,
  database: "noreon_demo",
  username: "noreon_ro",
  password: "",
};

export default function Home() {
  const [conns, setConns] = useState<Connection[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CreateResult | null>(null);

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
      const res = await api.createConnection({ ...form, port: Number(form.port) });
      setResult(res);
      setForm({ ...EMPTY });
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
          Sources enregistrées. Noreon vérifie que le compte est en{" "}
          <strong>lecture seule</strong> avant toute analyse.
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
                <div className="font-medium">{c.name}</div>
                <div className="text-xs text-noreon-soft mono">
                  {c.username}@{c.host}:{c.port}/{c.database}
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
          <h2 className="font-semibold">Nouvelle connexion PostgreSQL</h2>
          <form onSubmit={submit} className="space-y-3">
            {(
              [
                ["name", "Nom", "text"],
                ["host", "Hôte", "text"],
                ["port", "Port", "number"],
                ["database", "Base", "text"],
                ["username", "Utilisateur", "text"],
                ["password", "Mot de passe", "password"],
              ] as const
            ).map(([key, label, type]) => (
              <div key={key}>
                <label className="text-xs text-noreon-soft">{label}</label>
                <input
                  className="input mono"
                  type={type}
                  required={key !== "password" ? key !== "port" : false}
                  value={(form as any)[key]}
                  onChange={(e) =>
                    setForm({ ...form, [key]: e.target.value })
                  }
                />
              </div>
            ))}
            <button className="btn-primary w-full justify-center" disabled={busy}>
              {busy ? "Test en cours…" : "Tester & enregistrer"}
            </button>
          </form>

          {error && (
            <div className="text-sm text-red-300 bg-red-500/10 rounded-lg p-3">
              {error}
            </div>
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
