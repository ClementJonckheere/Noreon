// =============================================================================
// Propagations E1..E4 — elles ORCHESTRENT plusieurs objets à la fois.
//
// Un événement ne se réduit pas à `transition(obj, event)` : E1 archive une
// définition, en crée une autre, recalcule les réponses non publiées, marque les
// conclusions publiées comme dépassées, crée un rapport v n+1, repasse des
// découvertes en revérification, traite une notification, écrit au journal.
//
// Chaque propagation est PURE : elle renvoie un PLAN d'effets (Effect[]) que la
// couche exécutante (aujourd'hui l'UI optimiste, demain FastAPI) applique. La
// grille B de la Carte v2 est reproduite ligne à ligne — une case vide = aucun
// effet (décision, pas oubli). Invariant R8 : on crée une révision ou une
// mention, on ne réécrit jamais un objet figé.
// =============================================================================

import type { ObjectKind, ObjectRef, ReportMention } from "./types";
import { canPublishAnswer, GuardResult } from "./guards";

export type Effect =
  | { kind: "set_state"; ref: ObjectRef; to: string; reason?: string }
  | { kind: "create"; create: ObjectKind; note: string; from?: ObjectRef }
  | { kind: "recalc_in_place"; ref: ObjectRef }
  | { kind: "add_mention"; report: string; mention: ReportMention }
  | { kind: "remove_mention"; report: string; mention: ReportMention; fromIncident?: string }
  | { kind: "journal"; actor: "noreon" | { human: string }; detail: string }
  | { kind: "notify"; to: string; action: string };

const ref = (kind: ObjectKind, id: string): ObjectRef => ({ kind, id });

// ── Action utilisateur « Publier » : produit une Conclusion (pas un état de
//    réponse). Gardée par R1/R3/R7. Retourne le plan, ou le refus de la garde.
export function publishAnswer(ctx: {
  answerId: string;
  state: Parameters<typeof canPublishAnswer>[0]["state"];
  blockingIncidentOnUsedSource: boolean;
}): { ok: true; effects: Effect[] } | Extract<GuardResult, { ok: false }> {
  const g = canPublishAnswer({
    state: ctx.state,
    blockingIncidentOnUsedSource: ctx.blockingIncidentOnUsedSource,
    willJournal: true,
  });
  if (!g.ok) return g;
  return {
    ok: true,
    effects: [
      { kind: "create", create: "conclusion", note: "figé par copie de la réponse publiée", from: ref("answer", ctx.answerId) },
      { kind: "journal", actor: { human: "utilisateur" }, detail: `Publication de la réponse ${ctx.answerId} → conclusion figée` },
    ],
  };
}

// ── E1 · Arbitrage rendu (la transition la plus coûteuse du produit).
export function propagateArbitration(ctx: {
  conceptId: string;
  unpublishedAnswers: string[];
  publishedConclusionsAffected: string[];
  validatedReport?: string;
  arbitrationQueueItem: string;
  discoveriesAffected: string[];
}): Effect[] {
  const e: Effect[] = [];
  // O3 — définition N archivée, N+1 en vigueur (origine de l'événement).
  e.push({ kind: "set_state", ref: ref("concept", ctx.conceptId), to: "archived", reason: "arbitrage rendu (E1)" });
  e.push({ kind: "create", create: "concept", note: "définition N+1 en vigueur" });
  // O1 — réponses non publiées recalculées en place.
  ctx.unpublishedAnswers.forEach((id) => e.push({ kind: "recalc_in_place", ref: ref("answer", id) }));
  // Conclusions publiées : dépassées, jamais réécrites (R8).
  ctx.publishedConclusionsAffected.forEach((id) =>
    e.push({ kind: "set_state", ref: ref("conclusion", id), to: "superseded", reason: "définition postérieure (E1)" }));
  // O2 — v n reste validé + prend la mention ; v n+1 créée en brouillon.
  if (ctx.validatedReport) {
    e.push({ kind: "add_mention", report: ctx.validatedReport, mention: "newer_definition" });
    e.push({ kind: "create", create: "report", note: "brouillon v n+1", from: ref("report", ctx.validatedReport) });
  }
  // O7 — découvertes → en revérification.
  ctx.discoveriesAffected.forEach((id) =>
    e.push({ kind: "set_state", ref: ref("discovery", id), to: "under_reverification", reason: "arbitrage (E1)" }));
  // O6 — l'élément d'arbitrage → traité ; deux revérifications entrent.
  e.push({ kind: "set_state", ref: ref("queue_item", ctx.arbitrationQueueItem), to: "processed" });
  ctx.discoveriesAffected.forEach(() => e.push({ kind: "create", create: "queue_item", note: "revérification de découverte" }));
  e.push({ kind: "journal", actor: "noreon", detail: `E1 arbitrage rendu sur concept ${ctx.conceptId}` });
  return e;
}

// ── E2 · Incident résolu (la propagation part de « résolu », pas de l'archivage).
export function propagateIncidentResolution(ctx: {
  incidentId: string;
  recalculatedAnswers: string[];
  reportsWithReserveMention: string[];
  incidentQueueItem: string;
}): Effect[] {
  const e: Effect[] = [];
  // O1 — réponses recalculées, mention de réserve retirée.
  ctx.recalculatedAnswers.forEach((id) => e.push({ kind: "recalc_in_place", ref: ref("answer", id) }));
  // O2 — mention retirée si elle venait de cet incident ; chiffres inchangés.
  ctx.reportsWithReserveMention.forEach((r) =>
    e.push({ kind: "remove_mention", report: r, mention: "later_incident", fromIncident: ctx.incidentId }));
  // O6 — l'élément d'incident → traité sans geste, signé par le contrôle.
  e.push({ kind: "set_state", ref: ref("queue_item", ctx.incidentQueueItem), to: "processed" });
  e.push({ kind: "journal", actor: "noreon", detail: `E2 incident ${ctx.incidentId} résolu (contrôle au vert)` });
  // O4 — émetteur : résolu puis archivé une fois la propagation terminée.
  e.push({ kind: "set_state", ref: ref("incident", ctx.incidentId), to: "archived", reason: "propagation E2 terminée" });
  return e;
}

// ── E3 · Accès accordé (aucun calcul avant le geste utilisateur, Q3).
export function propagateAccessGranted(ctx: {
  accessId: string;
  partialAnswers: string[];
  requesterId: string;
}): Effect[] {
  const e: Effect[] = [];
  // O5 — émetteur : accordé, expiration 90 j annoncée.
  e.push({ kind: "set_state", ref: ref("access", ctx.accessId), to: "granted", reason: "accès accordé (90 j)" });
  // O1 — périmètre partiel → reprise disponible (pas de recalcul auto, Q3).
  ctx.partialAnswers.forEach((id) =>
    e.push({ kind: "set_state", ref: ref("answer", id), to: "resume_available", reason: "accès accordé — attend « Reprendre »" }));
  // O6 — entrée « Reprendre l'analyse » créée pour le demandeur.
  e.push({ kind: "create", create: "queue_item", note: "Reprendre l'analyse" });
  e.push({ kind: "notify", to: ctx.requesterId, action: "Reprendre l'analyse" });
  e.push({ kind: "journal", actor: "noreon", detail: `E3 accès ${ctx.accessId} accordé` });
  return e;
}

// ── E4 · Scan terminé (recalcul automatique : le périmètre était déjà autorisé).
export function propagateScanCompleted(ctx: {
  partialAnswers: string[];
  failedControls: string[];
  stewardId: string;
}): Effect[] {
  const e: Effect[] = [];
  // O1 — périmètre partiel → en cours, recalcul automatique.
  ctx.partialAnswers.forEach((id) => {
    e.push({ kind: "set_state", ref: ref("answer", id), to: "running", reason: "scan terminé — périmètre connu" });
    e.push({ kind: "recalc_in_place", ref: ref("answer", id) });
  });
  // O3 — concepts candidats proposés (relations candidates ajoutées).
  e.push({ kind: "create", create: "concept", note: "candidats proposés sur le périmètre rescanné" });
  // O4 — ouverture possible si un contrôle échoue sur le schéma rescanné.
  ctx.failedControls.forEach(() => e.push({ kind: "create", create: "incident", note: "contrôle échoué sur le schéma rescanné" }));
  // O7 — nouvelles candidates produites.
  e.push({ kind: "create", create: "discovery", note: "candidates sur le périmètre rescanné" });
  // O6 — entrée « Confirmer les concepts proposés » pour l'intendant.
  e.push({ kind: "create", create: "queue_item", note: "Confirmer les concepts proposés" });
  e.push({ kind: "notify", to: ctx.stewardId, action: "Confirmer les concepts proposés" });
  e.push({ kind: "journal", actor: "noreon", detail: "E4 scan terminé" });
  return e;
}
