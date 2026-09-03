"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/ui/Icon";
import { api, NotificationsView, WorkItemKind } from "@/lib/api";
import { setCurrentSpaceId } from "@/lib/space";

// Cloche = deux primitives : À TRAITER (WorkItem, exige une action) et SUIVI
// (ActivityEvent, informe). Le badge compte les À TRAITER — un état MÉTIER, pas
// la lecture : « tout marquer comme lu » ne le fait jamais tomber à zéro.
// Centre USER-GLOBAL : chaque ligne commence par son espace réel ; un CTA
// inter-espace ACTIVE le bon espace avant d'ouvrir l'objet.
const KIND: Record<WorkItemKind, { label: string; action: string; href: (o: string) => string }> = {
  concept_arbitration: { label: "Concept", action: "Arbitrer", href: (o) => `/concepts/${o}` },
  relation_validation: { label: "Relation", action: "Examiner", href: (o) => `/relations/${o}` },
  measurement_due: { label: "Mesure", action: "Mesurer", href: () => `/plan` },
  report_validation: { label: "Rapport", action: "Voir le rapport", href: (o) => `/reports/${o}` },
  quality_review: { label: "Qualité", action: "Voir", href: () => `/quality` },
  access_approval: { label: "Accès", action: "Approuver", href: () => `/admin/users` },
};

function ago(iso: string | null): string {
  if (!iso) return "";
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return "il y a quelques minutes";
  if (h < 48) return `il y a ${Math.round(h)} h`;
  return `il y a ${Math.round(h / 24)} j`;
}

export default function NotificationBell() {
  const router = useRouter();
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

  // CTA inter-espace : on ACTIVE l'espace de l'objet AVANT de naviguer, pour ne
  // jamais atterrir sur la page vide de l'espace courant.
  function goTo(spaceId: number | null, href: string) {
    if (spaceId != null) setCurrentSpaceId(spaceId);
    setOpen(false);
    router.push(href);
  }

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
        <div className="absolute right-0 top-full mt-1.5 w-[380px] z-40 card p-0 shadow-lg flex flex-col max-h-[70vh]">
          <div className="px-4 py-3 border-b border-line-subtle shrink-0">
            <div className="text-label uppercase text-ink-tertiary">Pour vous</div>
          </div>

          {/* Contenu défilant : 20 WorkItems n'agrandissent pas le panneau. */}
          <div className="overflow-y-auto min-h-0">
            <div className="px-4 py-3 space-y-3">
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
                        <div className="meta">
                          {w.space_label} · {k?.label ?? w.kind}{w.scope_label ? ` · ${w.scope_label}` : ""}
                        </div>
                        <div className="meta">{w.reason}</div>
                      </div>
                      <button onClick={() => goTo(w.space_id, k?.href(w.object_id) ?? "#")}
                        className="btn-secondary btn-sm shrink-0">{k?.action ?? "Ouvrir"}</button>
                    </div>
                  );
                })
              )}
            </div>

            {(data?.activity ?? []).length > 0 && (
              <div className="px-4 py-3 border-t border-line-subtle space-y-2.5">
                <div className="text-label uppercase text-ink-tertiary">Suivi</div>
                {(data?.activity ?? []).slice(0, 8).map((e) => (
                  <div key={e.id} className="min-w-0">
                    <div className="text-small text-ink-secondary truncate">{e.title}</div>
                    <div className="meta flex items-center gap-1.5">
                      <span>{e.space_label} · {e.detail}</span>
                      <span className="text-line-strong">·</span>
                      <span className="mono">{ago(e.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
