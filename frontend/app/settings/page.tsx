"use client";

import { useEffect, useState } from "react";
import { api, AnalysisContext } from "@/lib/api";

// Contexte d'entreprise (D) — les conventions d'analyse que Noreon connaît et
// ne redemande plus. Paramétrage réservé à l'administrateur.
const GRAINS: { value: AnalysisContext["period_grain"]; label: string }[] = [
  { value: null, label: "Automatique" },
  { value: "day", label: "Quotidienne" },
  { value: "week", label: "Hebdomadaire" },
  { value: "month", label: "Mensuelle" },
  { value: "quarter", label: "Trimestrielle" },
  { value: "year", label: "Annuelle" },
];

export default function SettingsPage() {
  const [ctx, setCtx] = useState<AnalysisContext | null>(null);
  const [conv, setConv] = useState("");
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.getAnalysisContext().then(setCtx).catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="card p-4 text-sm text-red-600">{err}</div>;
  if (!ctx) return <div className="text-sm text-noreon-soft">Chargement…</div>;

  function set<K extends keyof AnalysisContext>(k: K, v: AnalysisContext[K]) {
    setCtx((c) => (c ? { ...c, [k]: v } : c));
    setSaved(false);
  }
  function addConvention() {
    const v = conv.trim();
    if (!v || !ctx) return;
    set("conventions", [...ctx.conventions, v]);
    setConv("");
  }
  async function save() {
    if (!ctx) return;
    setBusy(true);
    try {
      const r = await api.updateAnalysisContext(ctx);
      setCtx(r);
      setSaved(true);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-6 fade-in">
      <div>
        <h1 className="text-lg font-semibold">Contexte d'entreprise</h1>
        <p className="text-sm text-noreon-soft">
          Les conventions d'analyse de votre entreprise. Noreon les applique et
          les affiche comme hypothèses — sans jamais les redemander.
        </p>
      </div>

      <div className="card p-5 space-y-4">
        <div>
          <label className="text-xs text-noreon-soft">Base monétaire par défaut</label>
          <div className="flex gap-2 mt-1">
            {([null, "TTC", "HT"] as const).map((b) => (
              <button
                key={String(b)}
                type="button"
                onClick={() => set("amount_basis", b)}
                className={`btn text-xs justify-center ${
                  ctx.amount_basis === b
                    ? "bg-noreon-accent text-white"
                    : "border border-noreon-border text-noreon-soft"
                }`}
              >
                {b === null ? "Automatique" : b}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs text-noreon-soft">Granularité temporelle par défaut</label>
          <select
            value={ctx.period_grain ?? ""}
            onChange={(e) => set("period_grain", (e.target.value || null) as AnalysisContext["period_grain"])}
            className="input mt-1"
          >
            {GRAINS.map((g) => (
              <option key={String(g.value)} value={g.value ?? ""}>{g.label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-noreon-soft">Conventions (périmètre, exclusions…)</label>
          <div className="flex flex-wrap gap-1.5 mt-1">
            {ctx.conventions.map((c, i) => (
              <span key={i} className="badge bg-slate-100 text-slate-700">
                {c}
                <button
                  onClick={() => set("conventions", ctx.conventions.filter((_, j) => j !== i))}
                  className="ml-1.5 text-slate-400 hover:text-red-600"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <input
              className="input"
              placeholder="ex. France uniquement"
              value={conv}
              onChange={(e) => setConv(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addConvention())}
            />
            <button type="button" onClick={addConvention} className="btn-ghost">Ajouter</button>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button onClick={save} disabled={busy} className="btn-primary">
            {busy ? "Enregistrement…" : "Enregistrer"}
          </button>
          {saved && <span className="text-xs text-emerald-700">Enregistré ✓</span>}
        </div>
      </div>
    </div>
  );
}
