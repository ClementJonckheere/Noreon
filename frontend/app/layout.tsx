import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Noreon — Data Analyst IA",
  description: "Comprendre. Relier. Éclairer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>
        <header className="border-b border-noreon-border bg-noreon-panel/60 backdrop-blur">
          <div className="mx-auto max-w-6xl px-6 py-3 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <span className="text-xl font-bold tracking-tight">Noreon</span>
              <span className="text-xs text-noreon-soft hidden sm:inline">
                Comprendre. Relier. Éclairer.
              </span>
            </Link>
            <span className="badge bg-noreon-accent/15 text-noreon-accent">V0.1</span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
