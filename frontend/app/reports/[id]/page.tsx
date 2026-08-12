"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  authHeaders,
  Connection,
  ReportBlock,
  ReportFull,
  ReportVersionFull,
} from "@/lib/api";
import ChartBlock from "@/components/ChartBlock";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function ReportEditor() {
  const params = useParams();
  const rid = Number(params.id);
  const [report, setReport] = useState<ReportFull | null>(null);
  const [conns, setConns] = useState<Connection[]>([]);
  const [prompt, setPrompt] = useState("");
  const [connId, setConnId] = useState<number | null>(null);
  const [deep, setDeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const [titleEdit, setTitleEdit] = useState(false);
  const [titleVal, setTitleVal] = useState("");
  const [validating, setValidating] = useState(false);
  const [viewing, setViewing] = useState<ReportVersionFull | null>(null);

  async function refresh() {
    setReport(await api.report(rid));
  }

  async function validate() {
    setValidating(true);
    try { setReport(await api.reportValidate(rid)); }
    finally { setValidating(false); }
  }
  useEffect(() => {
    refresh();
    api.listConnections().then((c) => {
      setConns(c);
      setConnId(c[0]?.id ?? null);
    });
  }, [rid]);

  if (!report) return <div className="text-noreon-soft">Chargement…</div>;

  async function generate() {
    if (!prompt.trim()) return;
    setBusy(true);
    try {
      setReport(await api.reportGenerate(rid, prompt.trim(), connId, deep));
      setPrompt("");
    } finally {
      setBusy(false);
    }
  }

  async function download(format: "docx" | "pdf" | "md") {
    const res = await fetch(api.reportExportUrl(rid, format), { headers: authHeaders() });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report!.title}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Link href="/reports" className="text-xs text-noreon-soft hover:underline">
          ← Rapports
        </Link>
      </div>

      <div className="flex items-center gap-2">
        {titleEdit ? (
          <input
            autoFocus
            className="input text-xl font-semibold"
            value={titleVal}
            onChange={(e) => setTitleVal(e.target.value)}
            onBlur={async () => {
              setTitleEdit(false);
              await api.reportRename(rid, titleVal || report.title);
              refresh();
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        ) : (
          <h1
            className="text-2xl font-semibold cursor-text"
            onClick={() => {
              setTitleVal(report.title);
              setTitleEdit(true);
            }}
            title="Cliquer pour renommer"
          >
            {report.title}
          </h1>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button className="btn-secondary btn-sm" disabled={validating || report.blocks.length === 0} onClick={validate}>
            {validating ? "Validation…" : "Valider cette version"}
          </button>
          <span className="w-px h-5 bg-line-subtle" />
          <button className="btn-ghost" onClick={() => download("docx")}>Word</button>
          <button className="btn-ghost" onClick={() => download("pdf")}>PDF</button>
          <button className="btn-ghost" onClick={() => download("md")}>Markdown</button>
        </div>
      </div>

      {/* Historique des versions validées — instantanés immuables. */}
      {(report.versions?.length ?? 0) > 0 && (
        <div className="card p-3 space-y-2">
          <div className="text-label uppercase text-ink-tertiary">Versions validées</div>
          <div className="flex flex-wrap gap-2">
            {report.versions!.map((v) => (
              <button
                key={v.version}
                onClick={async () => setViewing(await api.reportVersion(rid, v.version))}
                className={`text-small rounded-field border px-2.5 py-1 transition-colors ${
                  viewing?.version === v.version ? "border-brand-300 bg-brand-50 text-brand-700" : "border-line-subtle text-ink-secondary hover:border-line-strong"
                }`}
                title={`Validée le ${fmtDate(v.created_at)}`}
              >
                v{v.version} · {fmtDate(v.created_at)}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Consultation d'une version figée — lecture seule, jamais éditable. */}
      {viewing && (
        <div className="space-y-3">
          <div className="state state-limit">
            <div className="state-title">Version v{viewing.version} — instantané validé le {fmtDate(viewing.created_at)}</div>
            <div className="state-body flex items-center gap-3">
              <span>Lecture seule : cette version ne change plus.</span>
              <button className="text-brand-700 hover:text-brand-800 underline" onClick={() => setViewing(null)}>
                Revenir au brouillon
              </button>
            </div>
          </div>
          {(viewing.blocks as ReportBlock[]).map((b, i) => (
            <div key={i} className="card p-4">
              {b.kind === "markdown" && <Markdown text={b.content?.text ?? ""} />}
              {b.kind === "chart" && (
                <div className="text-small text-ink-tertiary flex items-center gap-2">
                  <span className="tag">Graphique</span>
                  <span>{b.content?.caption ?? "figé dans cette version"}</span>
                </div>
              )}
              {b.kind === "table" && (
                <div className="text-small text-ink-tertiary flex items-center gap-2">
                  <span className="tag">Tableau</span>
                  <span>{b.content?.caption ?? `${(b.content?.rows ?? []).length} ligne(s)`}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Demander à l'IA — masqué quand on consulte une version figée. */}
      {!viewing && (
      <div className="card p-3 space-y-2">
        <div className="text-sm font-medium">Demander à l'IA</div>
        <textarea
          rows={2}
          className="input resize-none"
          placeholder="Ex. « Rapport sur l'évolution du chiffre d'affaires par mois »"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs text-noreon-soft">Source</label>
          <select
            className="input w-auto"
            value={connId ?? ""}
            onChange={(e) => setConnId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Aucune (plan à compléter)</option>
            {conns.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <label className="text-xs flex items-center gap-1">
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />
            Analyse approfondie
          </label>
          <button className="btn-primary ml-auto" disabled={busy || !prompt.trim()} onClick={generate}>
            {busy ? "Génération…" : "Générer / Ajouter"}
          </button>
        </div>
      </div>
      )}

      {/* Incident POSTÉRIEUR : une réserve de qualité est apparue sur une table
          du rapport après sa validation. Le rapport reste tel qu'il a été publié
          — on prévient, on ne réécrit pas la conclusion. */}
      {(report.posterior_incidents?.length ?? 0) > 0 && (
        <div className="state state-abstain mb-3">
          <div className="state-title">Incident postérieur à la validation</div>
          <div className="state-body space-y-1">
            <p>
              Ce rapport reste tel qu'il a été validé. Depuis, un contrôle qualité a relevé
              une réserve sur les données qu'il utilise :
            </p>
            <ul className="space-y-0.5">
              {report.posterior_incidents!.map((it, i) => (
                <li key={i}>
                  <span className="font-mono">{it.ref}</span> — {it.dimension.toLowerCase()} · réserve
                  {it.since ? ` (dernière valeur : ${it.since})` : ""}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Blocs du rapport (brouillon éditable) — masqués en consultation de version. */}
      {!viewing && (
        <>
          <div className="space-y-3">
            {report.blocks.length === 0 && (
              <div className="card p-6 text-sm text-noreon-soft">
                Rapport vide. Demandez à l'IA ci-dessus, ou ajoutez un bloc de texte.
              </div>
            )}
            {report.blocks.map((b, i) => (
              <BlockView
                key={b.id}
                rid={rid}
                block={b}
                first={i === 0}
                last={i === report.blocks.length - 1}
                onChange={refresh}
              />
            ))}
          </div>

          <button
            className="btn-ghost"
            onClick={async () => {
              await api.reportAddBlock(rid, "markdown", { text: "Nouveau paragraphe." });
              refresh();
            }}
          >
            + Bloc de texte
          </button>
        </>
      )}
    </div>
  );
}

function BlockView({
  rid,
  block,
  first,
  last,
  onChange,
}: {
  rid: number;
  block: ReportBlock;
  first: boolean;
  last: boolean;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(block.content?.text ?? "");

  return (
    <div className="card p-4 group relative">
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 flex gap-1 text-xs">
        {block.kind === "markdown" && (
          <button
            className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? "Aperçu" : "Éditer"}
          </button>
        )}
        <button
          className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-30"
          disabled={first}
          onClick={() => api.reportMoveBlock(rid, block.id, "up").then(onChange)}
        >
          ↑
        </button>
        <button
          className="px-2 py-0.5 rounded bg-slate-100 hover:bg-slate-200 disabled:opacity-30"
          disabled={last}
          onClick={() => api.reportMoveBlock(rid, block.id, "down").then(onChange)}
        >
          ↓
        </button>
        <button
          className="px-2 py-0.5 rounded bg-red-500/10 text-red-600 hover:bg-red-500/20"
          onClick={() => api.reportDeleteBlock(rid, block.id).then(onChange)}
        >
          Suppr
        </button>
      </div>

      {block.kind === "markdown" &&
        (editing ? (
          <div className="space-y-2">
            <textarea
              className="input resize-y min-h-[8rem] mono text-xs"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <button
              className="btn-primary"
              onClick={async () => {
                await api.reportUpdateBlock(rid, block.id, { text });
                setEditing(false);
                onChange();
              }}
            >
              Enregistrer
            </button>
          </div>
        ) : (
          <Markdown text={block.content?.text ?? ""} />
        ))}

      {block.kind === "table" && (
        <div>
          {block.content?.caption && (
            <div className="text-sm font-medium mb-2">{block.content.caption}</div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-noreon-soft border-b border-noreon-border">
                <tr>
                  {(block.content?.columns ?? []).map((c: any) => (
                    <th key={c} className="text-left px-3 py-1.5">{String(c)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(block.content?.rows ?? []).slice(0, 60).map((r: any[], i: number) => (
                  <tr key={i} className="border-b border-noreon-border/60">
                    {r.map((v, j) => <td key={j} className="px-3 py-1 mono">{String(v ?? "")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {block.kind === "chart" && (
        <div>
          {block.content?.caption && (
            <div className="text-sm font-medium mb-2">{block.content.caption}</div>
          )}
          {block.content?.columns && (
            <ChartBlock
              columns={block.content.columns}
              rows={block.content.rows ?? []}
              suggestion={block.content.chart}
            />
          )}
        </div>
      )}
    </div>
  );
}

// Rendu Markdown minimal (titres, listes, paragraphes).
function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-sm">
      {lines.map((raw, i) => {
        const line = raw.trimEnd();
        if (!line) return <div key={i} className="h-1" />;
        if (line.startsWith("### ")) return <h3 key={i} className="text-base font-semibold mt-2">{line.slice(4)}</h3>;
        if (line.startsWith("## ")) return <h2 key={i} className="text-lg font-semibold mt-3">{line.slice(3)}</h2>;
        if (line.startsWith("# ")) return <h1 key={i} className="text-xl font-bold mt-3">{line.slice(2)}</h1>;
        if (line.startsWith("- ") || line.startsWith("* "))
          return <li key={i} className="ml-5 list-disc">{line.slice(2).replace(/\*\*/g, "")}</li>;
        return <p key={i}>{line.replace(/\*\*/g, "")}</p>;
      })}
    </div>
  );
}
