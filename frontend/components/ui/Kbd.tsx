"use client";

import { useEffect, useState } from "react";

// Raccourci clavier neutre côté serveur, puis adapté à la plateforme au montage
// (⌘ sur macOS, Ctrl ailleurs) — Noreon se développe aussi pour Windows.
export default function Kbd({ letter = "K", className = "kbd" }: { letter?: string; className?: string }) {
  const [mod, setMod] = useState("Ctrl");
  useEffect(() => {
    const p = navigator.platform || navigator.userAgent || "";
    setMod(/mac|iphone|ipad|ipod/i.test(p) ? "⌘" : "Ctrl");
  }, []);
  return <span className={className}>{mod === "⌘" ? `⌘${letter}` : `Ctrl ${letter}`}</span>;
}
