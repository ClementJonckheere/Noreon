// =============================================================================
// Transitions LOCALES — elles changent UN seul objet d'état.
//
// À distinguer strictement des propagations (E1..E4), qui orchestrent plusieurs
// objets et vivent dans propagations.ts. Ici, tout est pur : (état, action) →
// verdict. Les gardes interdites (R*/Q3) sont consultées le cas échéant.
// =============================================================================

import type {
  AnswerState, ConclusionState, ReportState, ConceptState,
  IncidentState, AccessState, QueueItemState, DiscoveryState,
} from "./types";
import { canPublishAnswer, canEditReportContent, canCloseIncidentManually, GuardResult } from "./guards";

export type TransitionOk<S> = { ok: true; next: S };
export type TransitionResult<S> = TransitionOk<S> | { ok: false; rule: string; reason: string };

const to = <S>(next: S): TransitionOk<S> => ({ ok: true, next });
const blocked = (g: Extract<GuardResult, { ok: false }>): TransitionResult<never> =>
  ({ ok: false, rule: g.rule, reason: g.reason });
const illegal = (reason: string): TransitionResult<never> => ({ ok: false, rule: "—", reason });

/* ── O1 · Réponse ─────────────────────────────────────────────────────────
   « publish » ne fait PAS transiter la réponse : il produit une Conclusion
   (voir propagations/publishAnswer). La réponse, elle, reste publishable.      */
export type AnswerAction =
  | "calc_below_threshold" | "calc_above_threshold"
  | "scope_partial" | "recalc_in_place";
export function transitionAnswer(state: AnswerState, action: AnswerAction): TransitionResult<AnswerState> {
  switch (action) {
    case "calc_below_threshold": return to<AnswerState>("below_threshold");
    case "calc_above_threshold": return to<AnswerState>("publishable");
    case "scope_partial":        return to<AnswerState>("partial");
    case "recalc_in_place":
      // Tant que non publiée, tout événement amont met à jour en place (une seule
      // ligne au journal). L'état ne « saute » pas, il reste investigable.
      if (state === "partial") return illegal("Un périmètre partiel se lève par E3/E4, pas par recalcul en place.");
      return to<AnswerState>("running");
  }
}

/* Publication : garde R1/R3/R7 ; le résultat est une Conclusion, pas un état de réponse. */
export function canPublish(a: { state: AnswerState; blockingIncidentOnUsedSource: boolean; willJournal: boolean }) {
  return canPublishAnswer(a);
}

/* ── Conclusion ───────────────────────────────────────────────────────────── */
export type ConclusionAction = "supersede" | "withdraw";
export function transitionConclusion(state: ConclusionState, action: ConclusionAction): TransitionResult<ConclusionState> {
  if (state !== "published") return illegal("Seule une conclusion publiée peut être dépassée ou retirée.");
  return action === "supersede" ? to<ConclusionState>("superseded") : to<ConclusionState>("withdrawn");
}

/* ── O2 · Rapport ─────────────────────────────────────────────────────────── */
export type ReportAction = "validate" | "create_next_version" | "withdraw";
export function transitionReport(state: ReportState, action: ReportAction): TransitionResult<ReportState> {
  switch (action) {
    case "validate":
      if (state !== "draft") return illegal("Seul un brouillon se valide.");
      return to<ReportState>("validated"); // figé par copie
    case "create_next_version": {
      // validé → brouillon v n+1 : création d'un OBJET nouveau, jamais une modif.
      const g = canEditReportContent({ state });
      if (state === "validated") return to<ReportState>("draft"); // le NOUVEL objet
      if (!g.ok) return blocked(g);
      return illegal("Une nouvelle version se crée depuis un rapport validé.");
    }
    case "withdraw":
      if (state !== "validated") return illegal("Seul un rapport validé peut être retiré (motif obligatoire).");
      return to<ReportState>("withdrawn");
  }
}

/* ── O3 · Concept ─────────────────────────────────────────────────────────── */
export type ConceptAction = "confirm" | "open_arbitration" | "archive";
export function transitionConcept(state: ConceptState, action: ConceptAction): TransitionResult<ConceptState> {
  switch (action) {
    case "confirm":
      if (state !== "candidate") return illegal("Seul un candidat se confirme (signature obligatoire, R7).");
      return to<ConceptState>("in_force");
    case "open_arbitration":
      if (state !== "in_force") return illegal("L'arbitrage s'ouvre sur une définition en vigueur.");
      return to<ConceptState>("arbitration_open");
    case "archive":
      // arbitrage → N archivée + N+1 en vigueur : la bascule est portée par E1.
      if (state !== "arbitration_open" && state !== "in_force")
        return illegal("Seule une définition en vigueur/arbitrée s'archive.");
      return to<ConceptState>("archived");
  }
}

/* ── O4 · Incident (fermeture manuelle interdite, R3) ───────────────────────── */
export type IncidentAction = "open_ticket" | "auto_resolve" | "archive";
export function transitionIncident(state: IncidentState, action: IncidentAction): TransitionResult<IncidentState> {
  switch (action) {
    case "open_ticket":
      if (state !== "open") return illegal("Un ticket s'ouvre sur un incident ouvert.");
      return to<IncidentState>("awaiting_source");
    case "auto_resolve":
      // Seul le retour au vert du contrôle referme (émet E2). Pas de bouton humain.
      if (state !== "open" && state !== "awaiting_source") return illegal("Rien à résoudre.");
      return to<IncidentState>("resolved");
    case "archive":
      if (state !== "resolved") return illegal("Un incident s'archive après propagation (E2), depuis « résolu ».");
      return to<IncidentState>("archived");
  }
}
// Aide UI : la fermeture manuelle est explicitement refusée.
export const denyManualIncidentClose = canCloseIncidentManually;

/* ── O5 · Accès (refus/expiration → demandable, jamais une sortie) ──────────── */
export type AccessAction = "request" | "grant" | "refuse" | "expire";
export function transitionAccess(state: AccessState, action: AccessAction): TransitionResult<AccessState> {
  switch (action) {
    case "request":
      if (state !== "requestable") return illegal("Seul un domaine demandable peut être demandé.");
      return to<AccessState>("pending_arbitration");
    case "grant":
      if (state !== "pending_arbitration") return illegal("On n'accorde qu'une demande en arbitrage.");
      return to<AccessState>("granted"); // émet E3, expiration 90 j
    case "refuse":
      if (state !== "pending_arbitration") return illegal("On ne refuse qu'une demande en arbitrage.");
      return to<AccessState>("requestable"); // motif visible ; jamais « non découvrable »
    case "expire":
      if (state !== "granted") return illegal("Seul un accès accordé expire.");
      return to<AccessState>("requestable");
  }
}

/* ── O6 · File « À traiter » (réassignation = event sans changement d'état) ──── */
export type QueueAction = "defer" | "resume" | "process" | "close";
export function transitionQueueItem(state: QueueItemState, action: QueueAction): TransitionResult<QueueItemState> {
  switch (action) {
    case "defer":
      if (state !== "to_process") return illegal("On ne reporte qu'un élément à traiter.");
      return to<QueueItemState>("deferred");
    case "resume":
      if (state !== "deferred") return illegal("On ne relance qu'un élément reporté.");
      return to<QueueItemState>("to_process");
    case "process": // peut être posé par une machine (E2), la ligne de journal nomme le contrôle.
      return to<QueueItemState>("processed");
    case "close": // échappatoire auditée (motif obligatoire, R7).
      return to<QueueItemState>("closed");
  }
}

/* ── O7 · Découverte (boucle de revérification) ─────────────────────────────── */
export type DiscoveryAction = "present" | "investigate" | "reverify" | "validate" | "dismiss" | "settle";
export function transitionDiscovery(state: DiscoveryState, action: DiscoveryAction): TransitionResult<DiscoveryState> {
  switch (action) {
    case "present":
      if (state !== "candidate") return illegal("Seule une candidate est présentée.");
      return to<DiscoveryState>("new");
    case "investigate":
      if (state !== "new") return illegal("Seule une nouvelle s'investigue.");
      return to<DiscoveryState>("investigated");
    case "reverify":
      // état transitoire imposé par E1 (une validée n'y retourne pas : elle est figée).
      if (state !== "new" && state !== "investigated") return illegal("Seule une découverte non figée repasse en revérification.");
      return to<DiscoveryState>("under_reverification");
    case "settle": // sortie de revérification après recalcul
      if (state !== "under_reverification") return illegal("Rien à stabiliser.");
      return to<DiscoveryState>("new");
    case "validate":
      if (state === "dismissed") return illegal("Une écartée ne se valide pas.");
      return to<DiscoveryState>("validated");
    case "dismiss":
      return to<DiscoveryState>("dismissed"); // motif obligatoire
  }
}
