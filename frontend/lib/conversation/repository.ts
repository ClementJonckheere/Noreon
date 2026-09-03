"use client";

import { api, ChatResponse } from "@/lib/api";

// =============================================================================
// ConversationRepository — la Conversation est un objet de PREMIER niveau.
// Les composants ne dépendent que de cette interface, jamais du backend actuel
// (conv* par connexion aujourd'hui, API Conversation dédiée demain). Adosser à
// l'Espace : une conversation agrège des sources, la source n'est qu'une
// dépendance résolue pendant l'investigation.
// =============================================================================

export interface ConversationSummary {
  id: string;            // identifiant global opaque (namespacé par l'adapter)
  title: string;
  sourceId: number;      // dépendance résolue (masquée dans l'UX, visible en Preuve)
  sourceName?: string;
  folderId: number | null;
  folderName?: string;
  updatedAt: string | null;
  turnCount: number;
}

export interface ConversationTurn {
  id: string;
  question: string;
  deep: boolean;
  response: ChatResponse | null;
  error: string | null;
}

export interface ConversationDetail {
  summary: ConversationSummary;
  turns: ConversationTurn[];
}

export interface ConversationRepository {
  list(): Promise<ConversationSummary[]>;
  get(id: string): Promise<ConversationDetail>;
  create(opts?: { folderId?: number | null }): Promise<ConversationSummary>;
  addMessage(id: string, question: string, deep: boolean): Promise<ConversationTurn>;
  hasSource(): Promise<boolean>;
}

// ── Adapter sur le backend actuel (conversations par connexion) ─────────────
// Id global = `${connectionId}.${conversationId}` → aucune requête pour résoudre
// la source. À remplacer par un adapter spaceConv*/API dédiée sans toucher aux
// composants.
const NS = ".";
const encode = (connId: number, convId: number) => `${connId}${NS}${convId}`;
const decode = (id: string): { connId: number; convId: number } => {
  const [c, v] = id.split(NS);
  return { connId: Number(c), convId: Number(v) };
};

class ConnectionConversationAdapter implements ConversationRepository {
  private async firstConnectionId(): Promise<number | null> {
    const conns = await api.listConnections().catch(() => []);
    return conns[0]?.id ?? null;
  }

  async hasSource(): Promise<boolean> {
    const conns = await api.listConnections().catch(() => []);
    return conns.length > 0;
  }

  async list(): Promise<ConversationSummary[]> {
    const conns = await api.listConnections().catch(() => []);
    const perConn = await Promise.all(
      conns.map(async (c) => {
        const convs = await api.convList(c.id, false).catch(() => []);
        return convs.map((cv) => ({
          id: encode(c.id, cv.id),
          title: cv.title,
          sourceId: c.id,
          sourceName: c.name,
          folderId: cv.folder_id ?? null,
          updatedAt: cv.updated_at ?? null,
          turnCount: cv.turn_count ?? 0,
        }));
      }),
    );
    return perConn.flat().sort((a, b) =>
      (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""));
  }

  async get(id: string): Promise<ConversationDetail> {
    const { connId, convId } = decode(id);
    const conn = await api.getConnection(connId).catch(() => null);
    const full = await api.convGet(connId, convId);
    return {
      summary: {
        id, title: full.title, sourceId: connId, sourceName: conn?.name,
        folderId: full.folder_id ?? null, updatedAt: full.updated_at ?? null,
        turnCount: full.turns.length,
      },
      turns: full.turns.map((t) => ({
        id: String(t.id), question: t.question, deep: t.deep, response: t.response, error: t.error,
      })),
    };
  }

  async create(opts?: { folderId?: number | null }): Promise<ConversationSummary> {
    const connId = await this.firstConnectionId();
    if (connId == null) throw new Error("Aucune source connectée à cet espace.");
    const conn = await api.getConnection(connId).catch(() => null);
    const cv = await api.convCreate(connId, { folder_id: opts?.folderId ?? null });
    return {
      id: encode(connId, cv.id), title: cv.title, sourceId: connId, sourceName: conn?.name,
      folderId: cv.folder_id ?? null, updatedAt: cv.updated_at ?? null, turnCount: 0,
    };
  }

  async addMessage(id: string, question: string, deep: boolean): Promise<ConversationTurn> {
    const { connId, convId } = decode(id);
    const { turn } = await api.convAddTurn(connId, convId, question, deep);
    return { id: String(turn.id), question: turn.question, deep: turn.deep, response: turn.response, error: turn.error };
  }
}

// Singleton — un seul point de bascule vers l'adapter cible plus tard.
let repo: ConversationRepository | null = null;
export function conversationRepository(): ConversationRepository {
  return (repo ??= new ConnectionConversationAdapter());
}
