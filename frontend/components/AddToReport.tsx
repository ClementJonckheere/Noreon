"use client";

import { useState } from "react";
import { api, ChatResponse, ReportSummary } from "@/lib/api";

// Bouton sous une réponse d'IA : l'ajouter (narratif + graphique + tableau) dans
// un rapport existant ou nouveau.
export default function AddToReport({
  response,
  title,
}: {
  response: ChatResponse;
  title: string;
}) {
  const [open, setOpen] = useState(false);
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (!open && reports === null) setReports(await api.reports());
    setOpen((o) => !o);
  }
  async function addTo(rid: number, name: string) {
    setBusy(true);
    try {
      await api.reportAddAnswer(rid, title || "Analyse", response);
      setDone(`Ajouté à « ${name} »`);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }
  async function createAndAdd() {
    setBusy(true);
    try {
      const r = await api.reportCreate(title || "Nouveau rapport");
      await api.reportAddAnswer(r.id, title || "Analyse", response);
      setDone(`Créé « ${r.title} »`);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  if (done) return <div className="text-xs text-emerald-700">✓ {done}</div>;

  return (
    <div className="relative inline-block text-xs">
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1 text-noreon-soft hover:text-slate-900"
        title="Ajouter cette réponse à un rapport"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}
          className="w-3.5 h-3.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 3h9l4 4v14H6z" /><path d="M15 3v4h4" /><path d="M12 11v6M9 14h6" />
        </svg>
        Ajouter à un rapport
      </button>
      {open && (
        <div className="absolute z-10 mt-1 w-56 card p-1 shadow-card">
          <button
            disabled={busy}
            onClick={createAndAdd}
            className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 text-noreon-accent"
          >
            + Nouveau rapport
          </button>
          {(reports ?? []).map((r) => (
            <button
              key={r.id}
              disabled={busy}
              onClick={() => addTo(r.id, r.title)}
              className="w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 truncate"
            >
              {r.title}
            </button>
          ))}
          {reports && reports.length === 0 && (
            <div className="px-2 py-1 text-noreon-soft">Aucun rapport existant.</div>
          )}
        </div>
      )}
    </div>
  );
}
