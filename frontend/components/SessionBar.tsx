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
      <Link href="/login" className="btn-secondary btn-sm w-full">
        Se connecter
      </Link>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2.5">
        <span className="grid place-items-center w-8 h-8 rounded-full bg-brand-100 text-brand-800 text-body font-medium shrink-0">
          {(me.email || "d")[0].toUpperCase()}
        </span>
        <div className="min-w-0 leading-tight">
          {me.email ? (
            <>
              <div className="text-body text-ink truncate">{me.email}</div>
              <div className="text-label uppercase text-ink-3">{ROLE_LABEL[me.role] || me.role}</div>
            </>
          ) : (
            <div className="text-body text-warning-hover">mode dev · admin implicite</div>
          )}
        </div>
      </div>
      {authed && (
        <button onClick={logout} className="text-small text-ink-3 hover:text-ink transition-colors">
          Déconnexion
        </button>
      )}
    </div>
  );
}
