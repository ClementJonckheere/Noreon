// Vérification à la COMPILATION (pas de runner de tests dans ce frontend) :
// chaque union d'état est couverte exhaustivement. Si un libellé de la Carte v2
// est ajouté sans être traité, `tsc` (via `next build`) échoue ici. Ce fichier
// n'exporte rien d'utile à l'exécution ; il ne sert qu'au type-check.

import type {
  AnswerState, ConclusionState, ReportState, ConceptState,
  IncidentState, AccessState, QueueItemState, DiscoveryState, PropagationEvent,
} from "./types";

// Un Record complet force tsc à exiger TOUS les membres de l'union.
const _answer: Record<AnswerState, true> = {
  running: true, partial: true, resume_available: true, below_threshold: true, publishable: true,
};
const _conclusion: Record<ConclusionState, true> = {
  published: true, superseded: true, withdrawn: true,
};
const _report: Record<ReportState, true> = {
  draft: true, validated: true, withdrawn: true,
};
const _concept: Record<ConceptState, true> = {
  candidate: true, in_force: true, arbitration_open: true, archived: true,
};
const _incident: Record<IncidentState, true> = {
  open: true, awaiting_source: true, resolved: true, archived: true,
};
const _access: Record<AccessState, true> = {
  non_discoverable: true, requestable: true, pending_arbitration: true, granted: true,
};
const _queue: Record<QueueItemState, true> = {
  to_process: true, deferred: true, processed: true, closed: true,
};
const _discovery: Record<DiscoveryState, true> = {
  candidate: true, new: true, investigated: true, under_reverification: true, validated: true, dismissed: true,
};
const _events: Record<PropagationEvent, true> = {
  E1_arbitration_rendered: true, E2_incident_resolved: true, E3_access_granted: true, E4_scan_completed: true,
};

// 32 états (brouillon compté une fois) + 4 événements. Empêche le tree-shaking
// de retirer les consts avant le type-check.
export const STATE_COUNTS = {
  answer: Object.keys(_answer).length,
  conclusion: Object.keys(_conclusion).length,
  report: Object.keys(_report).length,
  concept: Object.keys(_concept).length,
  incident: Object.keys(_incident).length,
  access: Object.keys(_access).length,
  queue: Object.keys(_queue).length,
  discovery: Object.keys(_discovery).length,
  events: Object.keys(_events).length,
};
