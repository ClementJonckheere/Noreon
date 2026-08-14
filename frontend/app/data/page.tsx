"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, Connection } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useCurrentSpace } from "@/lib/space";
import PipelineRibbon from "@/components/PipelineRibbon";
import SubNav from "@/components/SubNav";
import AccessDenied from "@/components/CapGate";

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
  const { caps, ready } = useSession();
  const { space } = useCurrentSpace();
  const [conns, setConns] = useState<Connection[] | null>(null);
  // Le panneau de connexion n'est PAS ouvert en permanence : c'est une action
  // ponctuelle. On liste d'abord, on connecte à la demande, on revient à la liste.
  const [panelOpen, setPanelOpen] = useState(false);
  const [engine, setEngine] = useState<string>("postgresql");
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const engineSpec = ENGINES.find((e) => e.id === engine)!;
  const isFile = engineSpec.kind === "file";

  async function load() {
    try {
      setConns(await api.listConnections());
    } catch {
      setConns([]);
    }
  }
  useEffect(() => {
    load();
  }, []);

  function openPanel() {
    setError(null);
    setForm({ ...EMPTY });
    if (fileRef.current) fileRef.current.value = "";
    setPanelOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (isFile) {
        const file = fileRef.current?.files?.[0];
        if (!file) throw new Error("Sélectionnez un fichier.");
        await api.uploadFileConnection(form.name, file);
      } else {
        await api.createConnection({
          ...form,
          engine,
          port: Number(form.port) || engineSpec.port,
        });
      }
      setForm({ ...EMPTY });
      if (fileRef.current) fileRef.current.value = "";
      await load();
      // Connexion réussie : on referme le panneau et on retourne à la liste.
      setPanelOpen(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (ready && !caps.viewData) return <AccessDenied />;

  const list = conns ?? [];
  const empty = conns !== null && list.length === 0;

  return (
    <div className="space-y-8 fade-in">
      <SubNav />
      <header className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-title text-ink">Sources de données</h1>
          <p className="text-body text-ink-2 max-w-reading">
            Le catalogue des sources du tenant, vérifiées en
            <span className="text-ink font-medium"> lecture seule</span>. Chaque source
            indique l'espace auquel elle est rattachée{space ? ` — les analyses de « ${space.name} » n'utilisent que les siennes` : ""}.
          </p>
        </div>
        {!empty && !panelOpen && (
          <button onClick={caps.manageSources ? openPanel : undefined} className="btn-primary btn-sm shrink-0"
            {...(!caps.manageSources ? { disabled: true, title: "Demandez une connexion à un administrateur" } : {})}>
            {caps.manageSources ? "Connecter une source" : "Demander une connexion"}
          </button>
        )}
      </header>

      {/* Le ruban pipeline n'apparaît qu'à l'onboarding (aucune source) : c'est un
          repère de démarrage, pas un ornement permanent. */}
      {(conns === null || empty) && <PipelineRibbon />}

      {conns === null ? (
        <div className="text-body text-ink-3">Chargement…</div>
      ) : empty ? (
        <div className="card p-8 text-center space-y-3">
          <div className="text-subhead text-ink">Aucune source connectée</div>
          <p className="text-body text-ink-3 max-w-reading mx-auto">
            Connectez une première source pour que Noreon puisse la profiler, en contrôler
            la qualité et en tirer des concepts. Tout se fait en lecture seule.
          </p>
          {caps.manageSources ? (
            <div className="pt-1"><button onClick={openPanel} className="btn-primary">Connecter une source</button></div>
          ) : (
            <div className="pt-1 meta">Demandez une connexion à un administrateur de l'espace.</div>
          )}
        </div>
      ) : (
        <section className="space-y-4">
          <div className="flex items-baseline gap-2">
            <h2 className="text-heading text-ink">Sources connectées</h2>
            <span className="meta">{list.length}</span>
          </div>
          <div className="space-y-2.5">
            {list.map((c) => (
              <Link
                key={c.id}
                href={`/connections/${c.id}`}
                className="card p-4 flex items-center justify-between hover:border-line-strong transition-colors"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-subhead text-ink truncate">{c.name}</span>
                    <span className="tag tag-neutral">
                      {ENGINES.find((e) => e.id === c.engine)?.label || c.engine}
                    </span>
                    <SpaceBadges spaces={c.spaces} current={space?.name} />
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
      )}

      {/* Panneau de connexion — temporaire, pas une colonne permanente. */}
      {panelOpen && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => !busy && setPanelOpen(false)}>
          <div className="w-full max-w-md h-full overflow-y-auto bg-bg-primary border-l border-line-subtle p-5 space-y-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="text-subhead text-ink">Connecter une source</h2>
              <button onClick={() => !busy && setPanelOpen(false)} className="btn-ghost btn-sm text-ink-3">Fermer</button>
            </div>

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
          </div>
        </div>
      )}
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

// Rattachement d'une source à un ou plusieurs espaces — l'espace courant est
// mis en avant ; « Non rattachée » lève l'ambiguïté (source du tenant sans espace).
function SpaceBadges({ spaces, current }: { spaces?: string[]; current?: string }) {
  const list = spaces ?? [];
  if (list.length === 0) return <span className="tag tag-neutral text-ink-tertiary">Non rattachée</span>;
  return (
    <span className="flex items-center gap-1 flex-wrap">
      {list.map((s) => (
        <span key={s} className={`tag ${s === current ? "bg-brand-100 text-brand-700 border-brand-200 border" : "tag-neutral"}`}>{s}</span>
      ))}
    </span>
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
