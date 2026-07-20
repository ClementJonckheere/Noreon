"use client";

// Persistance locale des conversations de chat (façon Claude) : historique par
// connexion, organisable en dossiers. Stockée dans le navigateur (localStorage)
// — aucune donnée d'analyse n'est renvoyée au serveur, seul le fil de questions
// et de réponses déjà obtenues est conservé côté client.
import { ChatResponse } from "./api";

export type Turn = {
  id: string;
  question: string;
  deep: boolean;
  response: ChatResponse | null;
  error?: string;
  ts: number;
};

export type Conversation = {
  id: string;
  title: string;
  folderId: string | null;
  turns: Turn[];
  createdAt: number;
  updatedAt: number;
};

export type Folder = { id: string; name: string };

export type ChatStore = {
  conversations: Conversation[];
  folders: Folder[];
  activeId: string | null;
};

const KEY = (connId: number) => `noreon.chat.${connId}`;

export function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export function emptyStore(): ChatStore {
  return { conversations: [], folders: [], activeId: null };
}

export function loadStore(connId: number): ChatStore {
  if (typeof window === "undefined") return emptyStore();
  try {
    const raw = window.localStorage.getItem(KEY(connId));
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as ChatStore;
    if (!parsed.conversations) return emptyStore();
    return parsed;
  } catch {
    return emptyStore();
  }
}

export function saveStore(connId: number, store: ChatStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY(connId), JSON.stringify(store));
  } catch {
    /* quota dépassé : on ignore silencieusement */
  }
}

export function newConversation(folderId: string | null = null): Conversation {
  const now = Date.now();
  return {
    id: uid(),
    title: "Nouvelle conversation",
    folderId,
    turns: [],
    createdAt: now,
    updatedAt: now,
  };
}

// Titre auto dérivé de la première question (tronqué proprement).
export function titleFrom(question: string): string {
  const t = question.trim().replace(/\s+/g, " ");
  return t.length > 42 ? t.slice(0, 42) + "…" : t || "Nouvelle conversation";
}
