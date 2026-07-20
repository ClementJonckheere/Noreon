"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  ChatResponse,
  Connection,
  Governance,
  Me,
  SpaceDetail,
  User,
} from "@/lib/api";
import AnswerView from "@/components/AnswerView";

type SpaceTab = "chat" | "sources" | "governance" | "members";

export default function SpaceWorkspace() {
  const params = useParams();
  const sid = Number(params.id);
  const [space, setSpace] = useState<SpaceDetail | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [tab, setTab] = useState<SpaceTab>("chat");

  async function refresh() {
    setSpace(await api.space(sid));
  }
  useEffect(() => {
    setMe(null);
    api.me().then(setMe).catch(() => setMe(null));
    refresh();
  }, [sid]);

  const isAdmin = !me || me.role === "admin";
  if (!space) return <div className="text-noreon-soft">Chargement…</div>;

  const tabs: [SpaceTab, string, boolean][] = [
    ["chat", "Chat", true],
    ["sources", "Sources", isAdmin],
    ["governance", "Gouvernance", isAdmin],
    ["members", "Membres", isAdmin],
  ];

  return (
    <div className="space-y-5">
      <div>
        <Link href="/spaces" className="text-xs text-noreon-soft hover:underline">
          ← Espaces
        </Link>
        <h1 className="text-2xl font-semibold">{space.name}</h1>
        <div className="text-xs text-noreon-soft">
          {space.connections.length} base(s) rattachée(s) · {space.members.length} membre(s)
        </div>
      </div>

      <nav className="flex gap-1 border-b border-noreon-border">
        {tabs.filter(([, , show]) => show).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${
              tab === t
                ? "border-noreon-accent text-slate-900"
                : "border-transparent text-noreon-soft hover:text-slate-900"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "chat" && <SpaceChat space={space} />}
      {tab === "sources" && isAdmin && <SourcesTab space={space} onChange={refresh} />}
      {tab === "governance" && isAdmin && <GovernanceTab space={space} />}
      {tab === "members" && isAdmin && <MembersTab space={space} onChange={refresh} />}
    </div>
  );
}

/* ------------------------------- CHAT --------------------------------- */
function SpaceChat({ space }: { space: SpaceDetail }) {
  const [connId, setConnId] = useState<number | null>(space.connections[0]?.id ?? null);
  const [q, setQ] = useState("");
  const [deep, setDeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const [thread, setThread] = useState<{ q: string; r: ChatResponse | null; err?: string }[]>([]);

  if (space.connections.length === 0) {
    return (
      <div className="card p-6 text-sm text-noreon-soft">
        Aucune base rattachée à cet espace. Un administrateur doit en ajouter dans l'onglet
        « Sources ».
      </div>
    );
  }

  async function ask() {
    const text = q.trim();
    if (!text || connId == null || busy) return;
    setThread((t) => [...t, { q: text, r: null }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.spaceChat(space.id, connId, text, deep);
      setThread((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, r } : x)));
    } catch (e: any) {
      setThread((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, err: e.message } : x)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="card p-3 flex items-center gap-3 flex-wrap">
        <label className="text-xs text-noreon-soft">Source</label>
        <select
          className="input w-auto"
          value={connId ?? ""}
          onChange={(e) => setConnId(Number(e.target.value))}
        >
          {space.connections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.engine})
            </option>
          ))}
        </select>
        <div className="inline-flex rounded-lg border border-noreon-border overflow-hidden text-sm ml-auto">
          <button
            onClick={() => setDeep(false)}
            className={`px-3 py-1.5 ${!deep ? "bg-slate-100 text-slate-900 font-medium" : "text-noreon-soft"}`}
          >
            ⚡ Rapide
          </button>
          <button
            onClick={() => setDeep(true)}
            className={`px-3 py-1.5 ${deep ? "bg-sky-500/15 text-sky-700 font-medium" : "text-noreon-soft"}`}
          >
            📊 Approfondie
          </button>
        </div>
      </div>

      {thread.map((t, i) => (
        <div key={i} className="space-y-3">
          <div className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl bg-noreon-accent/12 border border-noreon-accent/25 px-4 py-2 text-sm">
              {t.q}
            </div>
          </div>
          {t.err && <div className="text-sm text-red-600 bg-red-500/10 rounded-lg p-3">{t.err}</div>}
          {t.r ? (
            <AnswerView r={t.r} />
          ) : (
            !t.err && <div className="text-sm text-noreon-soft">Analyse en cours…</div>
          )}
        </div>
      ))}

      <div className="relative">
        <textarea
          rows={2}
          className="input resize-none pr-12"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          placeholder="Posez une question sur les données autorisées de cet espace…"
        />
        <button
          onClick={ask}
          disabled={busy || !q.trim()}
          className="absolute right-2 bottom-2 w-8 h-8 rounded-full bg-noreon-accent text-white flex items-center justify-center disabled:opacity-40"
        >
          ↑
        </button>
      </div>
    </div>
  );
}

/* ------------------------------ SOURCES ------------------------------- */
function SourcesTab({ space, onChange }: { space: SpaceDetail; onChange: () => void }) {
  const [all, setAll] = useState<Connection[]>([]);
  useEffect(() => {
    api.listConnections().then(setAll).catch(() => setAll([]));
  }, []);
  const attachedIds = new Set(space.connections.map((c) => c.id));
  const available = all.filter((c) => !attachedIds.has(c.id));

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="space-y-2">
        <div className="text-sm font-medium">Bases rattachées</div>
        {space.connections.length === 0 && (
          <div className="text-xs text-noreon-soft">Aucune base rattachée.</div>
        )}
        {space.connections.map((c) => (
          <div key={c.id} className="card p-3 flex items-center justify-between">
            <div>
              <div className="text-sm">{c.name}</div>
              <div className="text-xs text-noreon-soft uppercase">{c.engine}</div>
            </div>
            <button
              onClick={() => api.spaceDetach(space.id, c.id).then(onChange)}
              className="text-xs text-red-600 hover:underline"
            >
              Retirer
            </button>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <div className="text-sm font-medium">Bases disponibles (univers)</div>
        {available.length === 0 && (
          <div className="text-xs text-noreon-soft">Toutes les bases sont déjà rattachées.</div>
        )}
        {available.map((c) => (
          <div key={c.id} className="card p-3 flex items-center justify-between">
            <div>
              <div className="text-sm">{c.name}</div>
              <div className="text-xs text-noreon-soft uppercase">{c.engine}</div>
            </div>
            <button
              onClick={() => api.spaceAttach(space.id, c.id).then(onChange)}
              className="text-xs text-noreon-accent hover:underline"
            >
              Rattacher
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------- GOUVERNANCE ----------------------------- */
function GovernanceTab({ space }: { space: SpaceDetail }) {
  const [connId, setConnId] = useState<number | null>(space.connections[0]?.id ?? null);
  const [gov, setGov] = useState<Governance | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function load(cid: number) {
    setGov(await api.governance(space.id, cid));
  }
  useEffect(() => {
    if (connId != null) load(connId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connId]);

  if (space.connections.length === 0) {
    return <div className="card p-6 text-sm text-noreon-soft">Rattachez d'abord une base.</div>;
  }

  async function toggleT(schema: string, table: string, enabled: boolean) {
    if (connId == null) return;
    await api.toggleTable(space.id, connId, schema, table, enabled);
    load(connId);
  }
  async function toggleC(schema: string, table: string, col: string, enabled: boolean) {
    if (connId == null) return;
    await api.toggleColumn(space.id, connId, schema, table, col, enabled);
    load(connId);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <label className="text-xs text-noreon-soft">Base</label>
        <select
          className="input w-auto"
          value={connId ?? ""}
          onChange={(e) => setConnId(Number(e.target.value))}
        >
          {space.connections.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <span className="text-xs text-noreon-soft">
          Décochez ce qui ne doit pas être accessible dans cet espace.
        </span>
      </div>

      {!gov ? (
        <div className="text-sm text-noreon-soft">Chargement…</div>
      ) : !gov.scanned ? (
        <div className="card p-6 text-sm text-noreon-soft">
          Cette base n'a pas encore de schéma scanné.
        </div>
      ) : (
        <div className="space-y-2">
          {gov.tables.map((t) => (
            <div key={t.table} className="card p-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={t.enabled}
                  onChange={(e) => toggleT(t.schema, t.table, e.target.checked)}
                />
                <button
                  className={`font-medium text-sm ${t.enabled ? "" : "line-through text-noreon-soft"}`}
                  onClick={() => setOpen(open === t.table ? null : t.table)}
                >
                  {t.table}
                </button>
                <span className="text-xs text-noreon-soft">
                  {t.columns.length} colonnes · {t.columns.filter((c) => c.enabled).length} autorisées
                </span>
                <button
                  className="ml-auto text-xs text-noreon-soft hover:text-slate-900"
                  onClick={() => setOpen(open === t.table ? null : t.table)}
                >
                  {open === t.table ? "▲ colonnes" : "▼ colonnes"}
                </button>
              </div>
              {open === t.table && (
                <div className="mt-2 grid sm:grid-cols-2 lg:grid-cols-3 gap-1">
                  {t.columns.map((c) => (
                    <label
                      key={c.name}
                      className={`flex items-center gap-2 text-xs px-2 py-1 rounded ${
                        t.enabled ? "" : "opacity-40"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={c.enabled}
                        disabled={!t.enabled}
                        onChange={(e) => toggleC(t.schema, t.table, c.name, e.target.checked)}
                      />
                      <span className={c.enabled ? "" : "line-through text-noreon-soft"}>
                        {c.name}
                      </span>
                      <span className="text-noreon-soft mono ml-auto">{c.data_type}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ----------------------------- MEMBRES -------------------------------- */
function MembersTab({ space, onChange }: { space: SpaceDetail; onChange: () => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [sel, setSel] = useState<number | "">("");
  useEffect(() => {
    api.users().then(setUsers).catch(() => setUsers([]));
  }, []);
  const memberIds = new Set(space.members.map((m) => m.user_id));
  const candidates = users.filter((u) => !memberIds.has(u.id));

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="space-y-2">
        <div className="text-sm font-medium">Membres de l'espace</div>
        {space.members.length === 0 && (
          <div className="text-xs text-noreon-soft">Aucun membre (les admins voient tout).</div>
        )}
        {space.members.map((m) => (
          <div key={m.user_id} className="card p-3 flex items-center justify-between">
            <div className="text-sm">{m.email} <span className="text-xs text-noreon-soft">· {m.role}</span></div>
            <button
              onClick={() => api.spaceRemoveMember(space.id, m.user_id).then(onChange)}
              className="text-xs text-red-600 hover:underline"
            >
              Retirer
            </button>
          </div>
        ))}
      </div>
      <div className="card p-4 space-y-3 h-fit">
        <div className="font-medium">Ajouter un membre</div>
        <select className="input" value={sel} onChange={(e) => setSel(Number(e.target.value))}>
          <option value="">Choisir un utilisateur…</option>
          {candidates.map((u) => (
            <option key={u.id} value={u.id}>{u.email} ({u.role})</option>
          ))}
        </select>
        <button
          className="btn-primary w-full justify-center"
          disabled={sel === ""}
          onClick={() => sel !== "" && api.spaceAddMember(space.id, sel).then(() => { setSel(""); onChange(); })}
        >
          Ajouter
        </button>
      </div>
    </div>
  );
}
