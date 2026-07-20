"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ReportSummary } from "@/lib/api";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  async function refresh() {
    setReports(await api.reports());
  }
  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  async function create() {
    const r = await api.reportCreate(title.trim() || undefined);
    setTitle("");
    router.push(`/reports/${r.id}`);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Rapports</h1>
        <p className="text-sm text-noreon-soft">
          Demandez à l'IA un rapport sur un sujet, éditez-le directement, puis exportez-le en
          Word ou PDF.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-2">
          {loading ? (
            <div className="text-sm text-noreon-soft">Chargement…</div>
          ) : reports.length === 0 ? (
            <div className="card p-6 text-sm text-noreon-soft">
              Aucun rapport. Créez-en un à droite.
            </div>
          ) : (
            reports.map((r) => (
              <Link
                key={r.id}
                href={`/reports/${r.id}`}
                className="card p-4 flex items-center justify-between hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium">{r.title}</div>
                  <div className="text-xs text-noreon-soft">{r.block_count} bloc(s)</div>
                </div>
                <span className="text-noreon-soft">→</span>
              </Link>
            ))
          )}
        </div>
        <div className="card p-4 space-y-3 h-fit">
          <div className="font-medium">Nouveau rapport</div>
          <input
            className="input"
            placeholder="Titre (optionnel)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
          />
          <button className="btn-primary w-full justify-center" onClick={create}>
            Créer
          </button>
        </div>
      </div>
    </div>
  );
}
