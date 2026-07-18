"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken, Me } from "@/lib/api";

const ROLE_LABEL: Record<string, string> = {
  admin: "administrateur",
  analyst: "analyste",
  reader: "lecteur",
};

export default function SessionBar() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(!!getToken());
    api.me().then(setMe).catch(() => setMe(null));
  }, []);

  function logout() {
    clearToken();
    setMe(null);
    setAuthed(false);
    router.push("/login");
  }

  if (!me) {
    return (
      <Link href="/login" className="badge bg-noreon-accent/15 text-noreon-accent">
        Se connecter
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-3 text-xs">
      {me.role === "admin" && (
        <Link href="/users" className="text-noreon-soft hover:text-white">
          Utilisateurs
        </Link>
      )}
      <span className="text-noreon-soft">
        {me.email ? (
          <>
            {me.email} · <span className="text-noreon-accent">{ROLE_LABEL[me.role] || me.role}</span>
          </>
        ) : (
          <span className="text-amber-200">mode dev (admin implicite)</span>
        )}
      </span>
      {authed && (
        <button onClick={logout} className="badge bg-white/5 text-noreon-soft hover:text-white">
          Déconnexion
        </button>
      )}
    </div>
  );
}
