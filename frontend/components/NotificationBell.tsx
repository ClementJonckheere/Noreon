"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { api, NotificationsView, WorkItemKind } from "@/lib/api";

// Cloche = deux primitives : À TRAITER (WorkItem, exige une action) et SUIVI
// (ActivityEvent, informe). Le badge compte les À TRAITER — un état MÉTIER, pas
// la lecture : « tout marquer comme lu » ne le fait jamais tomber à zéro.
const KIND: Record<WorkItemKind, { label: string; action: string; href: (o: string) => string }> = {
  concept_arbitration: { label: "Concept", action: "Arbitrer", href: (o) => `/concepts/${o}` },
  relation_validation: { label: "Relation", action: "Examiner", href: (o) => `/relations/${o}` },
  measurement_due: { label: "Mesure", action: "Mesurer", href: () => `/plan` },
  report_validation: { label: "Rapport", action: "Voir le rapport", href: (o) => `/reports/${o}` },
  quality_review: { label: "Qualité", action: "Voir", href: () => `/quality` },
  access_approval: { label: "Accès", action: "Approuver", href: () => `/admin/users` },
};

export default function NotificationBell() {
  const [data, setData] = useState<NotificationsView | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = () => api.notifications().then(setData).catch(() => setData(null));
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!open) return;
    // À l'ouverture : marquer lu (efface les pastilles) — SANS toucher au compteur.
    api.notificationsMarkRead().then(setData).catch(() => {});
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const count = data?.to_process_count ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button type="button" aria-label="Notifications" onClick={() => setOpen((v) => !v)}
        className="relative grid place-items-center w-9 h-9 rounded-button text-ink-secondary hover:bg-bg-secondary transition-colors">
        <Icon name="bell" className="w-[18px] h-[18px]" />
        {count > 0 && (
          <span className="absolute top-1 right-1 min-w-[15px] h-[15px] px-1 grid place-items-center rounded-full bg-brand-600 text-white text-[10px] font-semibold leading-none">
            {count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 w-[360px] max-h-[70vh] overflow-y-auto z-40 card p-0 shadow-lg">
          <div className="px-4 py-3 border-b border-line-subtle">
            <div className="text-label uppercase text-ink-tertiary">Pour vous</div>
          </div>

          {/* À TRAITER — chaque item ouvre son workflow réel. */}
          <div className="px-4 py-3 space-y-2.5">
            <div className="text-label uppercase text-ink-tertiary">À traiter · {count}</div>
            {(data?.to_process ?? []).length === 0 ? (
              <div className="text-small text-ink-tertiary">Rien à traiter pour le moment.</div>
            ) : (
              (data?.to_process ?? []).map((w) => {
                const k = KIND[w.kind];
                return (
                  <div key={w.id} className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-small text-ink-primary truncate">{w.title}</div>
                      <div className="meta">{w.space_label} · {k?.label ?? w.kind}</div>
                      <div className="meta">{w.reason}</div>
                    </div>
                    <Link href={k?.href(w.object_id) ?? "#"} onClick={() => setOpen(false)}
                      className="btn-secondary btn-sm shrink-0">{k?.action ?? "Ouvrir"}</Link>
                  </div>
                );
              })
            )}
          </div>

          {/* SUIVI — informationnel, aucune action. */}
          {(data?.activity ?? []).length > 0 && (
            <div className="px-4 py-3 border-t border-line-subtle space-y-2">
              <div className="text-label uppercase text-ink-tertiary">Suivi</div>
              {(data?.activity ?? []).slice(0, 6).map((e) => (
                <div key={e.id} className="min-w-0">
                  <div className="text-small text-ink-secondary truncate">{e.title}</div>
                  <div className="meta">{e.space_label} · {e.detail}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
