"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AnswerView from "@/components/AnswerView";
import RightPanel from "@/components/conversation/RightPanel";
import Icon from "@/components/ui/Icon";
import {
  conversationRepository, ConversationDetail, ConversationTurn,
} from "@/lib/conversation/repository";

// Écran 03/04 — la Conversation est l'objet racine. Centre :
//   Question → Investigation → Réponse → Recommandation.
// Droite : panneau contextuel (Comprendre / Preuve / Source). La source n'est
// qu'une dépendance, visible dans la Preuve — jamais le parent de l'écran.
export default function ConversationScreen({ id }: { id: string }) {
  const repo = conversationRepository();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [q, setQ] = useState("");
  const [deep, setDeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const askedRef = useRef(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    repo.get(id).then((d) => { if (alive) { setDetail(d); setTurns(d.turns); } }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);

  // Question passée par l'accueil (barre « Que souhaitez-vous comprendre ? »).
  useEffect(() => {
    const initial = searchParams.get("q");
    if (initial && detail && !askedRef.current) {
      askedRef.current = true;
      ask(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  async function ask(question: string, deepMode = deep) {
    const text = question.trim();
    if (!text || busy) return;
    const tmp: ConversationTurn = { id: "pending-" + Date.now(), question: text, deep: deepMode, response: null, error: null };
    setTurns((t) => [...t, tmp]);
    setQ("");
    setBusy(true);
    try {
      const turn = await repo.addMessage(id, text, deepMode);
      setTurns((t) => t.map((x) => (x.id === tmp.id ? turn : x)));
    } catch (e: any) {
      setTurns((t) => t.map((x) => (x.id === tmp.id ? { ...x, error: e.message } : x)));
    } finally {
      setBusy(false);
    }
  }

  const lastAnswered = [...turns].reverse().find((t) => t.response)?.response ?? null;
  const title = turns.find((t) => t.question)?.question ?? detail?.summary.title ?? "Conversation";

  return (
    <div className="flex h-full min-h-0">
      {/* Centre — le fil. */}
      <section className="flex-1 min-w-0 flex flex-col">
        <div className="h-[60px] shrink-0 flex items-center px-8 border-b border-line-subtle">
          <div className="min-w-0">
            <div className="text-label uppercase text-ink-tertiary">Conversation</div>
            <h1 className="text-subhead text-ink-primary truncate">{title}</h1>
          </div>
        </div>

        <div ref={threadRef} className="flex-1 overflow-y-auto px-8 py-6">
          <div className="max-w-[720px] mx-auto space-y-6">
            {turns.length === 0 && !busy && (
              <div className="pt-8 text-center space-y-1">
                <div className="text-heading text-ink-primary">Que souhaitez-vous comprendre ?</div>
                <p className="text-body text-ink-tertiary">Posez une question sur vos données en langage naturel.</p>
              </div>
            )}
            {turns.map((t) => (
              <div key={t.id} className="space-y-3">
                <div className="flex justify-end">
                  <div className="max-w-[80%] rounded-card bg-brand-100 border border-brand-200 px-4 py-2 text-body text-ink-primary">
                    {t.question}
                  </div>
                </div>
                {t.error ? (
                  <div className="state state-blocker">
                    <div className="state-title">Blocage</div>
                    <div className="state-body">{t.error}</div>
                  </div>
                ) : t.response ? (
                  <AnswerView r={t.response} connectionId={detail?.summary.sourceId} mode="centre" />
                ) : (
                  <div className="text-body text-reasoning flex items-center gap-2">
                    <span className="reasoning-dots"><span /><span /><span /></span>
                    {t.deep ? "Analyse approfondie en cours…" : "Analyse en cours…"}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Composer */}
        <div className="shrink-0 border-t border-line-subtle bg-bg-secondary px-8 py-3">
          <div className="max-w-[720px] mx-auto space-y-2">
            <div className="flex items-center gap-3">
              <div className="inline-flex rounded-button border border-line overflow-hidden text-body">
                <button onClick={() => setDeep(false)} className={`px-3 py-1.5 transition-colors ${!deep ? "bg-surface-raised text-ink-primary font-medium" : "text-ink-tertiary hover:text-ink-primary"}`}>Rapide</button>
                <button onClick={() => setDeep(true)} className={`px-3 py-1.5 transition-colors ${deep ? "bg-reasoning-subtle text-reasoning font-medium" : "text-ink-tertiary hover:text-ink-primary"}`}>Approfondie</button>
              </div>
            </div>
            <div className="relative">
              <textarea
                ref={inputRef}
                rows={2}
                className="field h-auto resize-none pr-12 py-2"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(q); } }}
                placeholder="Posez une question…  (Entrée pour envoyer, Maj+Entrée pour un saut de ligne)"
              />
              <button
                onClick={() => ask(q)}
                disabled={busy || !q.trim()}
                aria-label="Envoyer"
                className="absolute right-2 bottom-2 w-8 h-8 rounded-full bg-brand-600 text-white grid place-items-center hover:bg-brand-700 disabled:bg-line-subtle disabled:text-ink-disabled transition-colors"
              >
                {busy ? "…" : <Icon name="plan" className="w-4 h-4 rotate-[-90deg]" />}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Droite — panneau contextuel (dès qu'une réponse existe). */}
      {lastAnswered && <RightPanel r={lastAnswered} />}
    </div>
  );
}
