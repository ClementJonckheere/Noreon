"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { conversationRepository } from "@/lib/conversation/repository";

// /conversations : redirige vers la plus récente, en crée une sinon. Sans
// source, état vide honnête (écran 28) plutôt qu'une conversation vide trompeuse.
export default function ConversationsIndex() {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "empty">("loading");

  useEffect(() => {
    const repo = conversationRepository();
    (async () => {
      if (!(await repo.hasSource())) return setState("empty");
      const list = await repo.list().catch(() => []);
      if (list[0]) return router.replace(`/conversations/${list[0].id}`);
      try {
        const c = await repo.create();
        router.replace(`/conversations/${c.id}`);
      } catch {
        setState("empty");
      }
    })();
  }, [router]);

  if (state === "loading") return <div className="p-8 text-body text-ink-tertiary">Chargement…</div>;
  return (
    <div className="p-8">
      <div className="max-w-reading mx-auto card p-8 text-center space-y-2 mt-10">
        <div className="text-subhead text-ink-primary">Aucune source à interroger</div>
        <p className="text-body text-ink-tertiary">
          Connectez une source à cet espace pour composer votre première analyse.
        </p>
        <div className="pt-2"><Link href="/data" className="btn-secondary">Voir les données</Link></div>
      </div>
    </div>
  );
}
