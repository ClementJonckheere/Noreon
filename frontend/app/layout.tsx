import "./globals.css";
import type { Metadata } from "next";
import { Instrument_Sans, JetBrains_Mono } from "next/font/google";
import Sidebar from "@/components/Sidebar";

// Instrument Sans pour tout ce qui se lit, JetBrains Mono pour tout ce qui se
// vérifie. Auto-hébergées par next/font (aucune requête réseau à l'exécution).
const sans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Noreon — Data Analyst IA",
  description: "Un outil rigoureux dont les réponses se lisent comme un rapport d'analyste.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${sans.variable} ${mono.variable}`}>
      <body className="font-sans">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          {/* Zone de lecture — papier chaud, largeur maîtrisée pour la lisibilité. */}
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-5xl px-8 py-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
