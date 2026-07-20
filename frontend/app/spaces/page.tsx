"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Me, Space } from "@/lib/api";

export default function SpacesPage() {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [me, setMe] = useState<Me | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setSpaces(await api.spaces());
  }
  useEffect(() => {
    (async () => {
      try {
        setMe(await api.me().catch(() => null));
        await refresh();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const isAdmin = !me || me.role === "admin"; // repli dev = admin

  async function create() {
    if (!name.trim()) return;
    setError(null);
    try {
      await api.spaceCreate(name.trim());
      setName("");
      refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Espaces</h1>
        <p className="text-sm text-noreon-soft">
          Un univers, plusieurs espaces d'équipe (CRM, Achat…). Chaque espace a son propre
          chat, son schéma et ses droits, et rattache une ou plusieurs bases.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-2">
          {loading ? (
            <div className="text-noreon-soft text-sm">Chargement…</div>
          ) : spaces.length === 0 ? (
            <div className="card p-6 text-sm text-noreon-soft">
              Aucun espace pour l'instant.
              {isAdmin && " Créez-en un à droite."}
            </div>
          ) : (
            spaces.map((s) => (
              <Link
                key={s.id}
                href={`/spaces/${s.id}`}
                className="card p-4 flex items-center justify-between hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs text-noreon-soft">
                    {s.connection_ids.length} base(s) rattachée(s)
                    {s.description ? ` · ${s.description}` : ""}
                  </div>
                </div>
                <span className="text-noreon-soft">→</span>
              </Link>
            ))
          )}
        </div>

        {isAdmin && (
          <div className="card p-4 space-y-3 h-fit">
            <div className="font-medium">Nouvel espace</div>
            <input
              className="input"
              placeholder="Nom (ex. CRM, Achat…)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && create()}
            />
            <button className="btn-primary w-full justify-center" onClick={create}>
              Créer l'espace
            </button>
            {error && <div className="text-xs text-red-600">{error}</div>}
            <p className="text-xs text-noreon-soft">
              Réservé aux administrateurs. Vous rattacherez ensuite les bases et gérerez la
              gouvernance (tables/colonnes) dans l'espace.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
