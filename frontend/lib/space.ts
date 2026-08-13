"use client";

import { useEffect, useState } from "react";
import { api, Space } from "@/lib/api";

// Espace courant + son MODE (demo | live). Le mode vient de l'objet Espace renvoyé
// par le backend ; un espace « démo » porte le scénario vitrine, un espace « live »
// ne mélange JAMAIS de données vitrines aux données réelles. L'espace sélectionné
// est PARTAGÉ (store léger + localStorage) pour que la barre supérieure et les
// pages cloisonnées par espace (Plan d'action…) restent synchronisées.
const ENV_DEMO = process.env.NEXT_PUBLIC_NOREON_DEMO_SPACE; // repli temporaire
const SEL_KEY = "noreon_space_id";

let cached: Promise<Space[]> | null = null;
function spacesOnce(): Promise<Space[]> {
  return (cached ??= api.spaces().catch(() => []));
}

// --- store partagé de l'espace sélectionné ---------------------------------
let selectedId: number | null = null;
const listeners = new Set<() => void>();
if (typeof window !== "undefined") {
  const raw = window.localStorage.getItem(SEL_KEY);
  selectedId = raw ? Number(raw) : null;
}
export function setCurrentSpaceId(id: number) {
  selectedId = id;
  if (typeof window !== "undefined") window.localStorage.setItem(SEL_KEY, String(id));
  listeners.forEach((fn) => fn());
}

function modeOf(space: Space | null): "demo" | "live" {
  if (space?.mode === "demo") return "demo";
  if (ENV_DEMO && space && String(space.id) === ENV_DEMO) return "demo";
  return "live";
}

/** Liste des espaces + sélection courante (pour le sélecteur de la barre). */
export function useSpaces(): {
  spaces: Space[]; current: Space | null; setCurrent: (id: number) => void; ready: boolean;
} {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [ready, setReady] = useState(false);
  const [, force] = useState(0);
  useEffect(() => {
    let alive = true;
    spacesOnce().then((list) => {
      if (!alive) return;
      setSpaces(list);
      if (selectedId == null || !list.some((s) => s.id === selectedId)) {
        if (list[0]) selectedId = list[0].id;   // défaut = 1er espace (sans persister)
      }
      setReady(true);
    });
    const fn = () => force((n) => n + 1);
    listeners.add(fn);
    return () => { alive = false; listeners.delete(fn); };
  }, []);
  const current = spaces.find((s) => s.id === selectedId) ?? spaces[0] ?? null;
  return { spaces, current, setCurrent: setCurrentSpaceId, ready };
}

export function useCurrentSpace(): { space: Space | null; mode: "demo" | "live"; ready: boolean } {
  const { current, ready } = useSpaces();
  return { space: current, mode: modeOf(current), ready };
}
