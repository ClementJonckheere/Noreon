"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

const ENGINES = [
  { id: "postgresql", label: "PostgreSQL", kind: "db", port: 5432 },
  { id: "mysql", label: "MySQL / MariaDB", kind: "db", port: 3306 },
  { id: "csv", label: "CSV", kind: "file" },
  { id: "excel", label: "Excel", kind: "file" },
] as const;

const EMPTY = { name: "", host: "localhost", port: 5432, database: "", username: "", password: "" };

// Formulaire d'import d'une base — utilisé pour créer une connexion depuis un
// espace. `onCreated(connectionId)` permet de la rattacher aussitôt.
export default function ImportConnection({
  onCreated,
}: {
  onCreated: (connectionId: number) => void | Promise<void>;
}) {
  const [engine, setEngine] = useState<string>("postgresql");
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const spec = ENGINES.find((e) => e.id === engine)!;
  const isFile = spec.kind === "file";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let res;
      if (isFile) {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("Sélectionnez un fichier.");
        res = await api.uploadFileConnection(form.name, file);
      } else {
        res = await api.createConnection({ ...form, engine, port: Number(form.port) || (spec as any).port });
      }
      await onCreated(res.connection.id);
      setForm({ ...EMPTY });
      if (fileRef.current) fileRef.current.value = "";
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 space-y-3">
      <div className="font-medium">Importer une base dans l'espace</div>
      <div className="flex flex-wrap gap-1">
        {ENGINES.map((e) => (
          <button
            key={e.id}
            type="button"
            onClick={() => setEngine(e.id)}
            className={`px-2.5 py-1 rounded-lg text-xs border ${
              engine === e.id ? "bg-noreon-accent text-white border-noreon-accent" : "border-noreon-border text-noreon-soft"
            }`}
          >
            {e.label}
          </button>
        ))}
      </div>
      <input
        className="input"
        placeholder="Nom"
        value={form.name}
        onChange={(e) => setForm({ ...form, name: e.target.value })}
        required
      />
      {isFile ? (
        <input ref={fileRef} type="file" accept={engine === "csv" ? ".csv" : ".xlsx,.xls"} className="text-xs" />
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <input className="input" placeholder="Hôte" value={form.host}
            onChange={(e) => setForm({ ...form, host: e.target.value })} />
          <input className="input" placeholder="Port" value={form.port}
            onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} />
          <input className="input col-span-2" placeholder="Base" value={form.database}
            onChange={(e) => setForm({ ...form, database: e.target.value })} />
          <input className="input" placeholder="Utilisateur" value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <input className="input" type="password" placeholder="Mot de passe" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
      )}
      <button className="btn-primary w-full justify-center" disabled={busy}>
        {busy ? "Import…" : "Importer et rattacher"}
      </button>
      {error && <div className="text-xs text-red-600">{error}</div>}
    </form>
  );
}
