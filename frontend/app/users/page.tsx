"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Connection, User } from "@/lib/api";

const ROLES = ["admin", "analyst", "reader"] as const;
const ROLE_LABEL: Record<string, string> = {
  admin: "administrateur",
  analyst: "analyste",
  reader: "lecteur",
};

const EMPTY = { email: "", password: "", full_name: "", role: "analyst" };

export default function UsersPage() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [conns, setConns] = useState<Connection[]>([]);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [grants, setGrants] = useState<Record<number, number[]>>({});
  const [expanded, setExpanded] = useState<number | null>(null);

  async function load() {
    try {
      setUsers(await api.users());
      setConns(await api.listConnections());
    } catch (e: any) {
      setError(e.message);
      setUsers([]);
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createUser(form);
      setForm({ ...EMPTY });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function changeRole(u: User, role: string) {
    await api.updateUser(u.id, { role }).catch((e) => setError(e.message));
    load();
  }
  async function toggleActive(u: User) {
    await api.updateUser(u.id, { is_active: !u.is_active }).catch((e) => setError(e.message));
    load();
  }
  async function remove(u: User) {
    await api.deleteUser(u.id).catch((e) => setError(e.message));
    load();
  }

  async function openGrants(u: User) {
    if (expanded === u.id) {
      setExpanded(null);
      return;
    }
    setExpanded(u.id);
    const list = await api.userConnections(u.id).catch(() => []);
    setGrants((g) => ({ ...g, [u.id]: list }));
  }
  async function toggleGrant(u: User, cid: number, granted: boolean) {
    if (granted) await api.revokeConnection(u.id, cid);
    else await api.grantConnection(u.id, cid);
    const list = await api.userConnections(u.id);
    setGrants((g) => ({ ...g, [u.id]: list }));
  }

  if (!users) return <div className="text-noreon-soft">Chargement…</div>;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-xs text-noreon-soft hover:underline">
          ← Connexions
        </Link>
        <h1 className="text-2xl font-semibold">Utilisateurs & rôles</h1>
        <p className="text-sm text-noreon-soft">
          Rôles : administrateur (gère tout), analyste (crée et analyse), lecteur
          (consulte et interroge). L’accès aux sources se gère par utilisateur.
        </p>
      </div>

      {error && (
        <div className="text-sm text-amber-700 bg-amber-500/10 rounded-lg p-3">{error}</div>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3 space-y-3">
          {users.map((u) => (
            <div key={u.id} className="card p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="font-medium">
                    {u.email}{" "}
                    {!u.is_active && <span className="badge bg-red-500/15 text-red-600">inactif</span>}
                    {u.mfa_enabled && <span className="badge bg-emerald-500/15 text-emerald-700 ml-1">MFA</span>}
                  </div>
                  <div className="text-xs text-noreon-soft">{u.full_name || "—"}</div>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="input !w-auto !py-1 text-xs"
                    value={u.role}
                    onChange={(e) => changeRole(u, e.target.value)}
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {ROLE_LABEL[r]}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <button className="btn-ghost !py-0.5 !px-2" onClick={() => openGrants(u)}>
                  Accès aux sources
                </button>
                <button className="btn-ghost !py-0.5 !px-2" onClick={() => toggleActive(u)}>
                  {u.is_active ? "Désactiver" : "Activer"}
                </button>
                <button className="btn-ghost !py-0.5 !px-2" onClick={() => remove(u)}>
                  Supprimer
                </button>
              </div>
              {expanded === u.id && (
                <div className="border-t border-noreon-border/40 pt-2 space-y-1">
                  {u.role === "admin" ? (
                    <div className="text-xs text-noreon-soft">
                      Un administrateur accède à toutes les sources.
                    </div>
                  ) : conns.length === 0 ? (
                    <div className="text-xs text-noreon-soft">Aucune source.</div>
                  ) : (
                    conns.map((c) => {
                      const granted = (grants[u.id] || []).includes(c.id);
                      return (
                        <label key={c.id} className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={granted}
                            onChange={() => toggleGrant(u, c.id, granted)}
                          />
                          <span>{c.name}</span>
                          <span className="badge bg-slate-100 text-noreon-soft">{c.engine}</span>
                        </label>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          ))}
          {users.length === 0 && (
            <div className="text-sm text-noreon-soft">
              Aucun utilisateur (mode dev). Créez-en un à droite.
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          <form onSubmit={createUser} className="card p-4 space-y-3">
            <h3 className="font-semibold text-sm">Nouvel utilisateur</h3>
            <Field label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} type="email" />
            <Field label="Nom" value={form.full_name} onChange={(v) => setForm({ ...form, full_name: v })} />
            <Field label="Mot de passe (≥ 8)" value={form.password} onChange={(v) => setForm({ ...form, password: v })} type="password" />
            <div>
              <label className="text-xs text-noreon-soft">Rôle</label>
              <select
                className="input"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn-primary w-full justify-center">Créer</button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="text-xs text-noreon-soft">{label}</label>
      <input
        className="input"
        type={type}
        required={type !== "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
