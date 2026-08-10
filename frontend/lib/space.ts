"use client";

import { useEffect, useState } from "react";
import { api, Space } from "@/lib/api";

// Espace courant + son MODE (demo | live). Le mode vient de l'objet Espace
// renvoyé par le backend (cible), avec repli sur une variable d'env le temps de
// la migration. Un espace « démo » porte le scénario vitrine ; un espace « live »
// ne mélange JAMAIS de données vitrines aux données réelles.
const ENV_DEMO = process.env.NEXT_PUBLIC_NOREON_DEMO_SPACE; // repli temporaire

let cached: Promise<Space[]> | null = null;
function spacesOnce(): Promise<Space[]> {
  return (cached ??= api.spaces().catch(() => []));
}

export function useCurrentSpace(): { space: Space | null; mode: "demo" | "live"; ready: boolean } {
  const [space, setSpace] = useState<Space | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let alive = true;
    spacesOnce().then((list) => {
      if (!alive) return;
      setSpace(list[0] ?? null);
      setReady(true);
    });
    return () => { alive = false; };
  }, []);

  const mode: "demo" | "live" =
    space?.mode === "demo"
      ? "demo"
      : ENV_DEMO && space && String(space.id) === ENV_DEMO
      ? "demo"
      : "live";
  return { space, mode, ready };
}
