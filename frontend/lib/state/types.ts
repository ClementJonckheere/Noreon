// =============================================================================
// Machine à états de Noreon — dérivée de « Carte des états v2 ».
//
// Sept objets à cycle de vie + la Conclusion (distincte de la Réponse et du
// Rapport, décision d'architecture). Source UNIQUE de vérité : aucun composant
// n'invente d'état ni n'implémente une transition hors de ce module.
//
// Identifiants en anglais (idiomatiques) ; le libellé Carte v2 est en commentaire.
// « Ce qui n'est pas un état » (sévérité, mention, réassignation) est modélisé
// comme attribut ou drapeau, jamais comme état.
// =============================================================================

/* ── O1 · Réponse d'analyse ───────────────────────────────────────────────
   Vit, se recalcule et se corrige tant qu'elle n'a pas franchi le seuil de
   l'espace. La publication ne la fait PAS passer « publiée » : elle produit une
   Conclusion (objet figé). D'où l'absence d'état terminal « published » ici.   */
export type AnswerState =
  | "running"           // en cours
  | "partial"           // périmètre partiel
  | "resume_available"  // reprise disponible (attend le geste « Reprendre », Q3)
  | "below_threshold"   // sous le seuil — investigable, non publiable (R1)
  | "publishable";      // au-dessus du seuil

/* ── Conclusion (nouvel objet) ────────────────────────────────────────────
   Le figé d'une réponse publiée : sa confiance, ses preuves, ses sources, ses
   concepts, ses limites, son statut de publication. Assemblée dans un rapport,
   jamais réécrite par une propagation amont (R8) — elle est « dépassée ».      */
export type ConclusionState =
  | "published"   // publiée
  | "superseded"  // dépassée (propagation amont : définition/incident postérieurs)
  | "withdrawn";  // retirée · motif

/* ── O2 · Rapport versionné ───────────────────────────────────────────────
   Embarque des instantanés immuables de conclusions. « validated » est terminal ;
   les mentions (définition plus récente, incident postérieur) sont des drapeaux,
   pas des états — leur seule action est de créer v n+1.                        */
export type ReportState =
  | "draft"       // brouillon v n
  | "validated"   // validé v n · figé (terminal)
  | "withdrawn";  // retiré · motif

/* ── O3 · Concept d'univers ─────────────────────────────────────────────── */
export type ConceptState =
  | "candidate"         // candidat
  | "in_force"          // définition N en vigueur
  | "arbitration_open"  // arbitrage ouvert
  | "archived";         // définition N archivée
// « Dérogation d'espace » : état PARALLÈLE, jamais un remplacement → drapeau.

/* ── O4 · Incident de qualité — la sévérité est un ATTRIBUT, pas un état ─── */
export type IncidentState =
  | "open"            // ouvert
  | "awaiting_source" // en attente côté source
  | "resolved"        // résolu — émet E2 (retour au vert du contrôle, pas un bouton, R3)
  | "archived";       // archivé — conséquence finale de la propagation E2
export type IncidentSeverity = "info" | "reserve" | "blocking"; // information · réserve · bloquant

/* ── O5 · Accès utilisateur × domaine ─────────────────────────────────────
   L'état zéro n'est pas « refusé » mais « non découvrable ». Refus et expiration
   ramènent à « demandable » (ce ne sont pas des sorties).                      */
export type AccessState =
  | "non_discoverable"    // non découvrable
  | "requestable"         // demandable
  | "pending_arbitration" // en attente d'arbitrage
  | "granted";            // accordé · 90 jours (émet E3)

/* ── O6 · Élément de la file « À traiter » ──────────────────────────────── */
export type QueueItemState =
  | "to_process" // à traiter
  | "deferred"   // reporté · date
  | "processed"  // traité
  | "closed";    // clos · motif (échappatoire auditée)
// Réassignation : ÉVÉNEMENT sans changement d'état → hors des états.

/* ── O7 · Découverte ──────────────────────────────────────────────────────
   Boucle de recalcul : nouvelle/investiguée → en revérification → recalcul →
   nouvelle/investiguée/écartée. Une validée est figée dans un rapport.         */
export type DiscoveryState =
  | "candidate"            // candidate
  | "new"                  // nouvelle (comptée par le badge Découvertes)
  | "investigated"         // investiguée
  | "under_reverification" // en revérification (seul état non terminal imposé par un événement)
  | "validated"            // validée
  | "dismissed";           // écartée · motif

/* ── Événements propagateurs (orchestrent plusieurs objets, voir propagations) ─ */
export type PropagationEvent =
  | "E1_arbitration_rendered" // arbitrage rendu
  | "E2_incident_resolved"    // incident résolu (la propagation part de « résolu »)
  | "E3_access_granted"       // accès accordé
  | "E4_scan_completed";      // scan terminé

/* ── Drapeaux d'un rapport validé — mentions, pas états ──────────────────── */
export type ReportMention = "newer_definition" | "later_incident";

/* États terminaux : on n'en sort qu'en créant l'objet suivant. */
export const TERMINAL_STATES = {
  conclusion: ["withdrawn"] as ConclusionState[],
  report: ["validated", "withdrawn"] as ReportState[],
  concept: ["archived"] as ConceptState[],
  incident: ["archived"] as IncidentState[],
  discovery: ["validated", "dismissed"] as DiscoveryState[],
} as const;

/* Référence d'objet (pour le journal, les propagations et l'audit). */
export type ObjectKind =
  | "answer" | "conclusion" | "report" | "concept"
  | "incident" | "access" | "queue_item" | "discovery";
export type ObjectRef = { kind: ObjectKind; id: string };
