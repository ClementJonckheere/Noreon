"use client";

import { usePathname } from "next/navigation";
import TopBar from "@/components/TopBar";

// Zone à droite de la sidebar : barre supérieure + zone de lecture (papier
// chaud, largeur maîtrisée). Sur les surfaces publiques (connexion), pas de
// chrome applicative.
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  if (pathname.startsWith("/login")) {
    return <main className="flex-1 overflow-y-auto">{children}</main>;
  }
  return (
    <div className="flex-1 flex flex-col min-w-0">
      <TopBar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
