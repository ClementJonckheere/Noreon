"use client";

import { usePathname } from "next/navigation";
import TopBar from "@/components/TopBar";

// Zone à droite de la sidebar : barre supérieure + zone de contenu. Les écrans
// de conversation sont pleine largeur (3 colonnes internes) ; les autres sont
// une zone de lecture centrée. Surfaces publiques (connexion) : pas de chrome.
export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  if (pathname.startsWith("/login")) {
    return <main className="flex-1 overflow-y-auto">{children}</main>;
  }
  const fullBleed = pathname.startsWith("/conversations");
  return (
    <div className="flex-1 flex flex-col min-w-0">
      <TopBar />
      {fullBleed ? (
        <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
      ) : (
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-8 py-8">{children}</div>
        </main>
      )}
    </div>
  );
}
