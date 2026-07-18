"use client";

// Alertes simples (V0.4). Surveillent une mesure (définition ou expression)
// et se déclenchent sur seuil ou chute en %. Évaluation via les garde-fous.

import { useEffect, useState } from "react";
import { api, Alert, AlertEvent, BusinessDefinition } from "@/lib/api";

const COMPARISONS: Record<string, string> = {
  gt: "dépasse le seuil",
  lt: "passe sous le seuil",
  pct_drop: "chute de plus de N%",
  pct_change: "varie de plus de N%",
};

const STATUS_STYLE: Record<string, string> = {
  triggered: "bg-red-500/15 text-red-300",
  ok: "bg-emerald-500/15 text-emerald-300",
  error: "bg-amber-500/15 text-amber-200",
  new: "bg-white/10 text-noreon-soft",
};

const EMPTY = {
  name: "",
  table_name: "",
  expression: "",
  filter_sql: "",
  comparison: "gt",
  threshold: 0,
  definition_id: "",
};

export default function AlertsPanel({ id }: { id: number }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [defs, setDefs] = useState<BusinessDefinition[]>([]);
  const [form, setForm] = useState<any>({ ...EMPTY });
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<Record<number, AlertEvent[]>>({});

  async function load() {
    setAlerts(await api.alerts(id).catch(() => []));
  }
  useEffect(() => {
    load();
    api.definitions().then((d) => setDefs(d.filter((x) => x.kind === "measure"))).catch(() => {});
  }, [id]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const useDef = form.definition_id !== "";
    try {
      await api.createAlert(id, {
        name: form.name,
        comparison: form.comparison,
        threshold: Number(form.threshold),
        definition_id: useDef ? Number(form.definition_id) : null,
        table_name: useDef ? null : form.table_name,
        expression: useDef ? null : form.expression,
        filter_sql: form.filter_sql || null,
      });
      setForm({ ...EMPTY });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function check(alertId: number) {
    await api.checkAlert(id, alertId).catch(() => {});
    load();
  }
  async function checkAll() {
    await api.checkAllAlerts(id).catch(() => {});
    load();
  }
  async function remove(alertId: number) {
    await api.deleteAlert(id, alertId).catch(() => {});
    load();
  }
  async function toggleEvents(alertId: number) {
    if (events[alertId]) {
      setEvents((e) => {
        const c = { ...e };
        delete c[alertId];
        return c;
      });
    } else {
      const ev = await api.alertEvents(id, alertId).catch(() => []);
      setEvents((e) => ({ ...e, [alertId]: ev }));
    }
  }

  if (!alerts) return <div className="text-noreon-soft">Chargement…</div>;

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-3 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Alertes ({alerts.length})</h3>
          {alerts.length > 0 && (
            <button className="btn-ghost text-xs" onClick={checkAll}>
              Tout vérifier
            </button>
          )}
        </div>
        {alerts.length === 0 && (
          <div className="text-xs text-noreon-soft">
            Aucune alerte. Créez-en une à droite (ex. « chute du CA de plus de 20% »).
          </div>
        )}
        {alerts.map((a) => (
          <div key={a.id} className="card p-4 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-sm font-medium">{a.name}</div>
                <div className="text-xs text-noreon-soft">
                  {a.definition_id ? "mesure liée" : `${a.expression} sur ${a.table_name}`} ·{" "}
                  {COMPARISONS[a.comparison]} ({a.threshold})
                </div>
              </div>
              <span className={`badge ${STATUS_STYLE[a.last_status] || STATUS_STYLE.new}`}>
                {a.last_status === "triggered" ? "déclenchée" : a.last_status}
              </span>
            </div>
            {a.last_message && (
              <div className="text-xs text-noreon-soft">{a.last_message}</div>
            )}
            <div className="flex flex-wrap gap-2 text-xs">
              <button className="btn-ghost !py-0.5 !px-2" onClick={() => check(a.id)}>
                Vérifier
              </button>
              <button className="btn-ghost !py-0.5 !px-2" onClick={() => toggleEvents(a.id)}>
                Historique
              </button>
              <button className="btn-ghost !py-0.5 !px-2" onClick={() => remove(a.id)}>
                Supprimer
              </button>
            </div>
            {events[a.id] && (
              <div className="mt-1 space-y-1 border-t border-noreon-border/40 pt-2">
                {events[a.id].length === 0 && (
                  <div className="text-xs text-noreon-soft">Aucune évaluation.</div>
                )}
                {events[a.id].map((ev) => (
                  <div key={ev.id} className="text-xs flex items-center gap-2">
                    <span className={`badge ${STATUS_STYLE[ev.status]}`}>{ev.status}</span>
                    <span className="text-noreon-soft">{ev.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="lg:col-span-2">
        <form onSubmit={submit} className="card p-4 space-y-3">
          <h3 className="font-semibold text-sm">Nouvelle alerte</h3>
          <Field label="Nom" value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="Chute du CA" />
          <div>
            <label className="text-xs text-noreon-soft">Mesure surveillée</label>
            <select
              className="input"
              value={form.definition_id}
              onChange={(e) => setForm({ ...form, definition_id: e.target.value })}
            >
              <option value="">— expression directe —</option>
              {defs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.expression})
                </option>
              ))}
            </select>
          </div>
          {form.definition_id === "" && (
            <>
              <Field label="Table" value={form.table_name} onChange={(v) => setForm({ ...form, table_name: v })} placeholder="orders" mono />
              <Field label="Expression" value={form.expression} onChange={(v) => setForm({ ...form, expression: v })} placeholder="sum(amount_ttc)" mono />
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-noreon-soft">Condition</label>
              <select
                className="input !py-2"
                value={form.comparison}
                onChange={(e) => setForm({ ...form, comparison: e.target.value })}
              >
                {Object.entries(COMPARISONS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <Field
              label="Seuil"
              value={String(form.threshold)}
              onChange={(v) => setForm({ ...form, threshold: v })}
              mono
            />
          </div>
          <button className="btn-primary w-full justify-center">Créer l'alerte</button>
          {error && <div className="text-xs text-red-300">{error}</div>}
        </form>
      </div>
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
