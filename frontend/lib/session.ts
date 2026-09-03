"use client";

import { useEffect, useState } from "react";
import { api, Me } from "@/lib/api";
import { capabilitiesForRole, Capabilities } from "@/lib/capabilities";

// Session partagée : une seule requête /me pour toute l'app (sidebar, header,
// pages). Les capacités en dérivent — navigation, actions, CTA, routes.
let cached: Promise<Me | null> | null = null;
function fetchMeOnce(): Promise<Me | null> {
  return (cached ??= api.me().catch(() => null));
}

export function useSession(): { me: Me | null; caps: Capabilities; ready: boolean } {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    fetchMeOnce().then((m) => alive && (setMe(m), setReady(true)));
    return () => { alive = false; };
  }, []);
  return { me, caps: capabilitiesForRole(me?.role), ready };
}
