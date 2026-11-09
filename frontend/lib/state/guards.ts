// =============================================================================
// Garde-fous — les 8 transitions interdites de la Carte v2 (R1..R8, Q3).
//
// Ce sont les invariants du produit : si l'une devient possible en cliquant, la
// maquette est fausse. Chaque garde est une fonction PURE renvoyant un verdict
// explicite (règle + motif) que l'UI affiche ; aucun composant ne réimplémente
// une de ces règles.
// =============================================================================

import type { AnswerState, AccessState, ConceptState, ReportState, IncidentSeverity } from "./types";

export type ForbiddenRule = "R1" | "R2" | "R3" | "R4" | "R6" | "R7" | "R8" | "Q3";
export type GuardResult = { ok: true } | { ok: false; rule: ForbiddenRule; reason: string };

const allow: GuardResult = { ok: true };
const deny = (rule: ForbiddenRule, reason: string): GuardResult => ({ ok: false, rule, reason });

// R1 + R3 + R7 — publier une réponse. Interdit sous le seuil (R1), si un incident
// bloquant pèse sur une source utilisée (R3), ou sans ligne de journal signée (R7).
export function canPublishAnswer(a: {
  state: AnswerState;
  blockingIncidentOnUsedSource: boolean;
  willJournal: boolean;
}): GuardResult {
  if (a.state === "below_threshold")
    return deny("R1", "Confiance sous le seuil de l'espace : investigable, non publiable.");
  if (a.state !== "publishable")
    return deny("R1", "Seule une réponse au-dessus du seuil peut être publiée.");
  if (a.blockingIncidentOnUsedSource)
    return deny("R3", "Un incident bloquant pèse sur une source utilisée.");
  if (!a.willJournal)
    return deny("R7", "Une publication doit être inscrite au journal (signée).");
  return allow;
}

// R2 — modifier un chiffre, une conclusion ou une confiance dans un rapport validé.
export function canEditReportContent(r: { state: ReportState }): GuardResult {
  if (r.state === "validated")
    return deny("R2", "Un rapport validé est figé : créez v n+1, il ne se modifie pas.");
  return allow;
}

// R3 — fermer un incident à la main. Seul le retour au vert du contrôle referme.
export function canCloseIncidentManually(): GuardResult {
  return deny("R3", "Un incident ne se ferme que par le retour au vert du contrôle automatique.");
}

// R3 — publier malgré un incident bloquant (garde dédiée, réutilisable).
export function blocksPublication(severity: IncidentSeverity): boolean {
  return severity === "blocking";
}

// R4 — redéfinir un concept d'univers depuis un espace sans dérogation motivée.
export function canRedefineConceptFromSpace(ctx: {
  fromSpace: boolean;
  hasMotivatedDerogation: boolean;
}): GuardResult {
  if (ctx.fromSpace && !ctx.hasMotivatedDerogation)
    return deny("R4", "Depuis un espace, un concept d'univers exige une dérogation motivée.");
  return allow;
}

// R8 — écraser une réponse publiée / conclusion figée / rapport historique au recalcul.
// Une propagation crée une révision ou pose une mention ; elle ne réécrit rien.
export function canOverwriteOnRecalc(): GuardResult {
  return deny("R8", "Une propagation crée une révision ou pose une mention ; elle ne réécrit jamais un objet figé.");
}

// Q3 — rejouer une analyse après un accès accordé sans geste explicite de l'utilisateur.
export function canAutoReplayAfterAccess(userRequested: boolean): GuardResult {
  if (!userRequested)
    return deny("Q3", "Après un accès accordé, l'analyse attend le geste « Reprendre l'analyse ».");
  return allow;
}

// R6 — un droit manquant ne s'affiche jamais comme un bouton grisé : soit une
// absence (rien), soit une demande. L'UI dérive son affordance d'ici.
export function accessAffordance(state: AccessState): "hidden" | "request" | "open" {
  switch (state) {
    case "non_discoverable":
      return "hidden"; // absence totale, jamais un bouton grisé
    case "requestable":
    case "pending_arbitration":
      return "request";
    case "granted":
      return "open";
  }
}

// R7 — tout changement d'état / sortie de file exige une ligne de journal signée.
export function requiresJournal(): true {
  return true;
}
