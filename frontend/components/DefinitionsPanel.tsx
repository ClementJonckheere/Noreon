"use client";

// Définitions métier réutilisables + préférences de l'entreprise (V0.4).
// Une mesure (« CA » = sum(amount_ttc)) ou un segment (« client fidèle »)
// définis ici sont réutilisés par le chat dans toutes les analyses.

import { useEffect, useState } from "react";
import { api, BusinessDefinition, Preferences } from "@/lib/api";

const CHART_TYPES = ["", "line", "bar", "pie", "scatter", "histogram"];
const CHART_LABELS: Record<string, string> = {
  "": "Automatique",
  line: "Courbe",
  bar: "Barres",
  pie: "Secteurs",
  scatter: "Nuage",
  histogram: "Histogramme",
};

const EMPTY = {
  name: "",
  kind: "measure",
  table_name: "",
  expression: "",
  filter_sql: "",
  description: "",
};

export default function DefinitionsPanel() {
  const [defs, setDefs] = useState<BusinessDefinition[] | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setDefs(await api.definitions().catch(() => []));
  }
  useEffect(() => {
    load();
    api.preferences().then(setPrefs).catch(() => {});
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createDefinition({
        ...form,
        expression: form.kind === "measure" ? form.expression : null,
        filter_sql: form.kind === "segment" ? form.filter_sql : form.filter_sql || null,
      });
      setForm({ ...EMPTY });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function remove(id: number) {
    await api.deleteDefinition(id).catch(() => {});
    load();
  }

  async function savePref(patch: Partial<Preferences>) {
    setPrefs(await api.updatePreferences(patch));
  }

  const measures = (defs || []).filter((d) => d.kind === "measure");
  const segments = (defs || []).filter((d) => d.kind === "segment");

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-3 space-y-5">
        {prefs && (
          <div className="card p-4 space-y-3">
            <h3 className="text-sm font-medium">Préférences de l'entreprise</h3>
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <label className="flex items-center gap-2">
                <span className="text-noreon-soft">Graphique par défaut</span>
                <select
                  className="input !w-auto !py-1"
                  value={prefs.preferred_chart_type ?? ""}
                  onChange={(e) =>
                    savePref({ preferred_chart_type: e.target.value || null })
                  }
                >
                  {CHART_TYPES.map((c) => (
                    <option key={c} value={c}>
                      {CHART_LABELS[c]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={prefs.auto_learn}
                  onChange={(e) => savePref({ auto_learn: e.target.checked })}
                />
                <span className="text-noreon-soft">
                  Apprentissage inter-connexions
                </span>
              </label>
            </div>
          </div>
        )}

        <Section title="Mesures" empty="Aucune mesure définie." items={measures}>
          {(d) => (
            <MetaRow
              key={d.id}
              title={d.name}
              body={`${d.expression} sur ${d.table_name}${d.filter_sql ? ` (filtre: ${d.filter_sql})` : ""}`}
              onDelete={() => remove(d.id)}
            />
          )}
        </Section>
        <Section title="Segments" empty="Aucun segment défini." items={segments}>
          {(d) => (
            <MetaRow
              key={d.id}
              title={d.name}
              body={`${d.table_name} où ${d.filter_sql}`}
              onDelete={() => remove(d.id)}
            />
          )}
        </Section>
      </div>

      <div className="lg:col-span-2">
        <form onSubmit={submit} className="card p-4 space-y-3">
          <h3 className="font-semibold text-sm">Nouvelle définition</h3>
          <div className="flex gap-2">
            {["measure", "segment"].map((k) => (
              <button
                type="button"
                key={k}
                onClick={() => setForm({ ...form, kind: k })}
                className={`btn text-xs ${
                  form.kind === k
                    ? "bg-noreon-accent text-white"
                    : "border border-noreon-border text-noreon-soft"
                }`}
              >
                {k === "measure" ? "Mesure" : "Segment"}
              </button>
            ))}
          </div>
          <Field label="Nom" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="CA, client fidèle…" />
          <Field label="Table" value={form.table_name} onChange={(v) => setForm({ ...form, table_name: v })} placeholder="orders" mono />
          {form.kind === "measure" ? (
            <Field label="Expression d'agrégat" value={form.expression} onChange={(v) => setForm({ ...form, expression: v })} placeholder="sum(amount_ttc)" mono />
          ) : (
            <Field label="Filtre SQL (WHERE)" value={form.filter_sql} onChange={(v) => setForm({ ...form, filter_sql: v })} placeholder="id IN (SELECT …)" mono />
          )}
          <Field label="Description" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
          <button className="btn-primary w-full justify-center">Enregistrer</button>
          {error && <div className="text-xs text-red-300">{error}</div>}
          <p className="text-xs text-noreon-soft">
            Une fois enregistrée, utilisez-la dans le chat : « CA par mois »,
            « combien de clients fidèles ».
          </p>
        </form>
      </div>
    </div>
  );
}

function Section({
  title,
  empty,
  items,
  children,
}: {
  title: string;
  empty: string;
  items: BusinessDefinition[];
  children: (d: BusinessDefinition) => React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {items.length === 0 ? (
        <div className="text-xs text-noreon-soft">{empty}</div>
      ) : (
        items.map(children)
      )}
    </section>
  );
}

function MetaRow({
  title,
  body,
  onDelete,
}: {
  title: string;
  body: string;
  onDelete: () => void;
}) {
  return (
    <div className="card p-3 flex items-start justify-between gap-2">
      <div>
        <div className="text-sm font-medium">{title}</div>
        <div className="text-xs text-noreon-soft mono break-all">{body}</div>
      </div>
      <button className="btn-ghost !py-0.5 !px-2 text-xs shrink-0" onClick={onDelete}>
        Supprimer
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="text-xs text-noreon-soft">{label}</label>
      <input
        className={`input ${mono ? "mono" : ""}`}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
