"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  ChatResponse,
  Connection,
  ConvFolder,
  ConvFull,
  ConvSummary,
  Governance,
  Me,
  SpaceDetail,
  User,
} from "@/lib/api";
import AnswerView from "@/components/AnswerView";
import ImportConnection from "@/components/ImportConnection";

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
type UiTurn = { id: string; question: string; r: ChatResponse | null; err?: string };

function SpaceChat({ space }: { space: SpaceDetail }) {
  const sid = space.id;
  const [connId, setConnId] = useState<number | null>(space.connections[0]?.id ?? null);
  const [deep, setDeep] = useState(true);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const [convs, setConvs] = useState<ConvSummary[]>([]);
  const [folders, setFolders] = useState<ConvFolder[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [turns, setTurns] = useState<UiTurn[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState("");
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (space.connections.length === 0) return;
    (async () => {
      const [fs, list] = await Promise.all([api.spaceFolderList(sid), api.spaceConvList(sid, false)]);
      setFolders(fs);
      if (list.length === 0) {
        const c = await api.spaceConvCreate(sid, {});
        setConvs([c]);
        select(c.id, c);
      } else {
        setConvs(list);
        select(list[0].id);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);

  if (space.connections.length === 0) {
    return (
      <div className="card p-6 text-sm text-noreon-soft">
        Aucune base rattachée à cet espace. Un administrateur doit en ajouter dans l'onglet
        « Sources ».
      </div>
    );
  }

  async function reload(archived = showArchived) {
    const list = await api.spaceConvList(sid, archived);
    setConvs(list);
    return list;
  }
  async function select(cid: number, full?: ConvFull) {
    setActiveId(cid);
    const conv = full ?? (await api.spaceConvGet(sid, cid));
    setTurns(conv.turns.map((t) => ({ id: String(t.id), question: t.question, r: t.response, err: t.error || undefined })));
  }

  async function ask() {
    const text = q.trim();
    if (!text || connId == null || busy) return;
    let cid = activeId;
    if (cid == null) {
      const c = await api.spaceConvCreate(sid, {});
      setConvs((cs) => [c, ...cs]);
      cid = c.id;
      setActiveId(cid);
    }
    const tmp = "pending-" + Date.now();
    setTurns((t) => [...t, { id: tmp, question: text, r: null }]);
    setQ("");
    setBusy(true);
    try {
      const { turn, conversation } = await api.spaceConvAddTurn(sid, cid, connId, text, deep);
      setTurns((t) => t.map((x) => (x.id === tmp ? { id: String(turn.id), question: turn.question, r: turn.response, err: turn.error || undefined } : x)));
      setConvs((cs) => [conversation, ...cs.filter((c) => c.id !== conversation.id)]);
    } catch (e: any) {
      setTurns((t) => t.map((x) => (x.id === tmp ? { ...x, err: e.message } : x)));
    } finally {
      setBusy(false);
    }
  }

  async function newConv(folderId: number | null = null) {
    if (showArchived) setShowArchived(false);
    const c = await api.spaceConvCreate(sid, { folder_id: folderId });
    if (!showArchived) setConvs((cs) => [c, ...cs]);
    setActiveId(c.id);
    setTurns([]);
  }
  async function delConv(cid: number) {
    await api.spaceConvDelete(sid, cid);
    const list = await reload();
    if (activeId === cid) (list[0] ? select(list[0].id) : newConv());
  }
  async function archive(cid: number, a: boolean) {
    await api.spaceConvUpdate(sid, cid, { archived: a });
    const list = await reload();
    if (activeId === cid) (list[0] ? select(list[0].id) : (showArchived ? setTurns([]) : newConv()));
  }

  const activeSummary = convs.find((c) => c.id === activeId);
  const matches = (c: ConvSummary) =>
    !search.trim() || c.title.toLowerCase().includes(search.trim().toLowerCase());
  const visible = convs.filter(matches);

  return (
    <div className="flex gap-4 h-[calc(100vh-18rem)] min-h-[460px]">
      <div className="flex-1 min-w-0 flex flex-col card overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2 border-b border-noreon-border flex-wrap">
          <div className="font-medium truncate flex-1 min-w-[8rem]">
            {activeSummary?.title ?? "Conversation"}
          </div>
          <label className="text-xs text-noreon-soft">Source</label>
          <select className="input w-auto py-1 text-xs" value={connId ?? ""} onChange={(e) => setConnId(Number(e.target.value))}>
            {space.connections.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <div className="inline-flex rounded-lg border border-noreon-border overflow-hidden text-xs">
            <button onClick={() => setDeep(false)} className={`px-2 py-1 ${!deep ? "bg-slate-100 text-slate-900 font-medium" : "text-noreon-soft"}`}>⚡</button>
            <button onClick={() => setDeep(true)} className={`px-2 py-1 ${deep ? "bg-sky-500/15 text-sky-700 font-medium" : "text-noreon-soft"}`}>📊</button>
          </div>
        </div>

        <div ref={threadRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
          {turns.length === 0 && !busy && (
            <div className="text-sm text-noreon-soft pt-4">
              Posez une question sur les données autorisées de cet espace.
            </div>
          )}
          {turns.map((t) => (
            <div key={t.id} className="space-y-3">
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl bg-noreon-accent/12 border border-noreon-accent/25 px-4 py-2 text-sm">
                  {t.question}
                </div>
              </div>
              {t.err && <div className="text-sm text-red-600 bg-red-500/10 rounded-lg p-3">{t.err}</div>}
              {t.r ? <AnswerView r={t.r} /> : !t.err && (
                <div className="text-sm text-noreon-soft flex items-center gap-2">
                  <span className="dots"><span /><span /><span /></span> Analyse en cours…
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="border-t border-noreon-border p-3">
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
              placeholder="Posez une question… (Entrée pour envoyer)"
            />
            <button onClick={ask} disabled={busy || !q.trim()}
              className="absolute right-2 bottom-2 w-8 h-8 rounded-full bg-noreon-accent text-white flex items-center justify-center disabled:opacity-40">↑</button>
          </div>
        </div>
      </div>

      {/* Historique de l'espace */}
      <aside className="w-56 shrink-0 hidden lg:flex flex-col card overflow-hidden">
        <div className="px-2 py-2 border-b border-noreon-border space-y-2">
          <button onClick={() => newConv()} className="btn-primary w-full justify-center text-xs">+ Conversation</button>
          {newFolder === null ? (
            <button onClick={() => setNewFolder("")} className="btn-ghost w-full justify-center text-xs text-slate-600">+ Dossier</button>
          ) : (
            <div className="flex gap-1">
              <input autoFocus className="input py-1 text-xs" placeholder="Dossier" value={newFolder}
                onChange={(e) => setNewFolder(e.target.value)}
                onKeyDown={async (e) => {
                  if (e.key === "Enter" && newFolder.trim()) { const f = await api.spaceFolderCreate(sid, newFolder.trim()); setFolders((fs) => [...fs, f]); setNewFolder(null); }
                  if (e.key === "Escape") setNewFolder(null);
                }} />
            </div>
          )}
          <div className="inline-flex w-full rounded-lg border border-noreon-border overflow-hidden text-xs">
            <button onClick={async () => { setShowArchived(false); await reload(false); }} className={`flex-1 py-1 ${!showArchived ? "bg-slate-100 text-slate-900 font-medium" : "text-noreon-soft"}`}>Actives</button>
            <button onClick={async () => { setShowArchived(true); await reload(true); }} className={`flex-1 py-1 ${showArchived ? "bg-slate-100 text-slate-900 font-medium" : "text-noreon-soft"}`}>Archivées</button>
          </div>
          <input className="input py-1 text-xs" placeholder="Rechercher…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1 text-sm">
          {folders.map((f) => (
            <div key={f.id}>
              <div className="flex items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wide text-noreon-soft">
                <span className="flex-1 truncate normal-case">{f.name}</span>
                <button onClick={() => newConv(f.id)} title="Nouvelle ici" className="hover:text-slate-900">+</button>
                <button onClick={async () => { await api.spaceFolderDelete(sid, f.id); setFolders((fs) => fs.filter((x) => x.id !== f.id)); reload(); }} className="hover:text-red-600">×</button>
              </div>
              {visible.filter((c) => c.folder_id === f.id).map((c) => (
                <SpaceConvRow key={c.id} c={c} active={c.id === activeId} archived={showArchived}
                  onSelect={() => select(c.id)} onDelete={() => delConv(c.id)} onArchive={() => archive(c.id, !showArchived)} />
              ))}
            </div>
          ))}
          {visible.filter((c) => !c.folder_id).map((c) => (
            <SpaceConvRow key={c.id} c={c} active={c.id === activeId} archived={showArchived}
              onSelect={() => select(c.id)} onDelete={() => delConv(c.id)} onArchive={() => archive(c.id, !showArchived)} />
          ))}
        </div>
      </aside>
    </div>
  );
}

function SpaceConvRow({ c, active, archived, onSelect, onDelete, onArchive }: {
  c: ConvSummary; active: boolean; archived: boolean;
  onSelect: () => void; onDelete: () => void; onArchive: () => void;
}) {
  return (
    <div className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 cursor-pointer ${active ? "bg-noreon-accent/12" : "hover:bg-slate-100"}`} onClick={onSelect}>
      <div className="flex-1 min-w-0">
        <div className={`truncate text-xs ${active ? "text-slate-900 font-medium" : "text-slate-700"}`}>{c.title}</div>
        <div className="text-[11px] text-noreon-soft">{c.turn_count} échange(s)</div>
      </div>
      <button onClick={(e) => { e.stopPropagation(); onArchive(); }} title={archived ? "Désarchiver" : "Archiver"} className="opacity-0 group-hover:opacity-100 text-noreon-soft hover:text-slate-900 text-xs">{archived ? "⤺" : "▤"}</button>
      <button onClick={(e) => { e.stopPropagation(); onDelete(); }} title="Supprimer" className="opacity-0 group-hover:opacity-100 text-noreon-soft hover:text-red-600 text-xs">×</button>
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
      <div className="space-y-3">
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
        <ImportConnection
          onCreated={async (cid) => {
            await api.spaceAttach(space.id, cid);
            await onChange();
          }}
        />
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
