// =============================================================================
// Capacités (capabilities) — la sidebar et les affordances dérivent d'un
// ENSEMBLE DE PERMISSIONS, jamais d'un `if (role === "analyste")` éparpillé
// dans React. Direction / Analyste / Opérationnel deviennent des ensembles de
// capacités, cohérents avec la gouvernance de Noreon.
//
// Les rôles applicatifs actuels (admin / analyst / reader) sont mappés vers les
// personas du design (direction / analyste / opérationnel).
// =============================================================================

export interface Capabilities {
  askQuestions: boolean;      // composer une analyse
  viewDiscoveries: boolean;   // Découvertes
  viewReports: boolean;       // Rapports
  viewPlan: boolean;          // Plan d'action
  viewData: boolean;          // Données (sources)
  inspectQuality: boolean;    // Qualité / contrôles
  manageConcepts: boolean;    // Concepts (Semantic Layer)
  validateRelation: boolean;  // valider une relation candidate — geste DISTINCT de l'arbitrage
  publishConclusion: boolean; // publier une conclusion
  validateConcept: boolean;   // valider/arbitrer un concept
  decideAction: boolean;      // retenir/instruire une décision
  administerSpace: boolean;   // gouvernance de l'espace
  manageSources: boolean;     // connecter/retirer une source (sinon : demander)
}

const NONE: Capabilities = {
  askQuestions: false, viewDiscoveries: false, viewReports: false, viewPlan: false,
  viewData: false, inspectQuality: false, manageConcepts: false, validateRelation: false,
  publishConclusion: false, validateConcept: false, decideAction: false,
  administerSpace: false, manageSources: false,
};

// Direction — décider. Voit les décisions instruites, pas l'atelier data.
const DIRECTION: Capabilities = {
  ...NONE,
  askQuestions: true, viewDiscoveries: true, viewReports: true, viewPlan: true,
  inspectQuality: true, publishConclusion: true, decideAction: true, administerSpace: true,
};

// Analyste — vérifier. L'atelier complet : données, qualité, concepts.
const ANALYSTE: Capabilities = {
  ...NONE,
  askQuestions: true, viewDiscoveries: true, viewReports: true,
  viewData: true, inspectQuality: true, manageConcepts: true, validateRelation: true,
  publishConclusion: true, validateConcept: true, manageSources: true,
};

// Opérationnel — agir. Son périmètre, ses actions, la lecture des rapports.
const OPERATIONNEL: Capabilities = {
  ...NONE,
  viewDiscoveries: true, viewReports: true, viewPlan: true,
};

export function capabilitiesForRole(role?: string | null): Capabilities {
  switch (role) {
    case "analyst": return ANALYSTE;
    case "reader": return OPERATIONNEL;
    case "admin": return { ...DIRECTION, viewData: true, inspectQuality: true, manageConcepts: true, validateRelation: true, validateConcept: true, manageSources: true };
    default: return DIRECTION; // mode dev / non authentifié : accueil dirigeant
  }
}
