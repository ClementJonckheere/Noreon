import { describe, it, expect } from "vitest";
import {
  canPublishAnswer, canEditReportContent, canCloseIncidentManually,
  canRedefineConceptFromSpace, canOverwriteOnRecalc, canAutoReplayAfterAccess,
  accessAffordance, blocksPublication,
} from "./guards";
import {
  transitionAnswer, transitionReport, transitionConcept, transitionIncident,
  transitionAccess, transitionDiscovery,
} from "./transitions";
import {
  publishAnswer, propagateArbitration, propagateIncidentResolution,
  propagateAccessGranted, propagateScanCompleted, Effect,
} from "./propagations";

// Tests ciblés : les 8 interdits (7 invariants R1,R2,R3,R4,R6,R7,R8 + la règle
// d'interaction Q3) et les 4 propagations E1..E4. Ce sont les assertions du
// contrat de la Carte v2 — ce qui doit rester vrai quand le moteur exécutera.

const has = (fx: Effect[], pred: (e: Effect) => boolean) => fx.some(pred);

describe("Guards — les 8 interdits", () => {
  it("R1 · publier une réponse sous le seuil est refusé", () => {
    const g = canPublishAnswer({ state: "below_threshold", blockingIncidentOnUsedSource: false, willJournal: true });
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R1");
  });

  it("une réponse au-dessus du seuil, sans incident, journalisée, est publiable", () => {
    expect(canPublishAnswer({ state: "publishable", blockingIncidentOnUsedSource: false, willJournal: true }).ok).toBe(true);
  });

  it("R3 · un incident bloquant interdit la publication", () => {
    const g = canPublishAnswer({ state: "publishable", blockingIncidentOnUsedSource: true, willJournal: true });
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R3");
    expect(blocksPublication("blocking")).toBe(true);
    expect(blocksPublication("reserve")).toBe(false);
  });

  it("R7 · publier sans ligne de journal signée est refusé", () => {
    const g = canPublishAnswer({ state: "publishable", blockingIncidentOnUsedSource: false, willJournal: false });
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R7");
  });

  it("R2 · on ne modifie pas le contenu d'un rapport validé (mais bien d'un brouillon)", () => {
    const validated = canEditReportContent({ state: "validated" });
    expect(validated.ok).toBe(false);
    if (!validated.ok) expect(validated.rule).toBe("R2");
    expect(canEditReportContent({ state: "draft" }).ok).toBe(true);
  });

  it("R3 · fermer un incident à la main est toujours refusé", () => {
    const g = canCloseIncidentManually();
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R3");
  });

  it("R4 · redéfinir un concept depuis un espace exige une dérogation", () => {
    const g = canRedefineConceptFromSpace({ fromSpace: true, hasMotivatedDerogation: false });
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R4");
    expect(canRedefineConceptFromSpace({ fromSpace: true, hasMotivatedDerogation: true }).ok).toBe(true);
  });

  it("R8 · un recalcul ne réécrit jamais un objet figé", () => {
    const g = canOverwriteOnRecalc();
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("R8");
  });

  it("Q3 · rejouer après accès accordé exige un geste explicite", () => {
    const g = canAutoReplayAfterAccess(false);
    expect(g.ok).toBe(false);
    if (!g.ok) expect(g.rule).toBe("Q3");
    expect(canAutoReplayAfterAccess(true).ok).toBe(true);
  });

  it("R6 · un droit manquant n'est jamais un bouton grisé (absence ou demande)", () => {
    expect(accessAffordance("non_discoverable")).toBe("hidden");
    expect(accessAffordance("requestable")).toBe("request");
    expect(accessAffordance("granted")).toBe("open");
  });
});

describe("Transitions locales", () => {
  it("réponse : calcul sous le seuil → below_threshold", () => {
    const r = transitionAnswer("running", "calc_below_threshold");
    expect(r.ok && r.next).toBe("below_threshold");
  });
  it("rapport : brouillon se valide, validé ne se re-modifie pas", () => {
    expect(transitionReport("draft", "validate")).toMatchObject({ ok: true, next: "validated" });
    expect(transitionReport("validated", "validate").ok).toBe(false);
  });
  it("incident : pas de fermeture manuelle, seul auto_resolve mène à résolu", () => {
    expect(transitionIncident("open", "auto_resolve")).toMatchObject({ ok: true, next: "resolved" });
  });
  it("accès : refus et expiration ramènent à demandable (pas une sortie)", () => {
    expect(transitionAccess("pending_arbitration", "refuse")).toMatchObject({ ok: true, next: "requestable" });
    expect(transitionAccess("granted", "expire")).toMatchObject({ ok: true, next: "requestable" });
  });
  it("découverte : boucle de revérification (une validée n'y retourne pas)", () => {
    expect(transitionDiscovery("investigated", "reverify")).toMatchObject({ ok: true, next: "under_reverification" });
    expect(transitionDiscovery("validated", "reverify").ok).toBe(false);
  });
  it("concept : un candidat se confirme en vigueur", () => {
    expect(transitionConcept("candidate", "confirm")).toMatchObject({ ok: true, next: "in_force" });
  });
});

describe("Publication → Conclusion", () => {
  it("publier une réponse publishable crée une Conclusion (pas un état de réponse)", () => {
    const r = publishAnswer({ answerId: "a1", state: "publishable", blockingIncidentOnUsedSource: false });
    expect(r.ok).toBe(true);
    if (r.ok) expect(has(r.effects, (e) => e.kind === "create" && e.create === "conclusion")).toBe(true);
  });
  it("publier sous le seuil est refusé par R1", () => {
    const r = publishAnswer({ answerId: "a1", state: "below_threshold", blockingIncidentOnUsedSource: false });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.rule).toBe("R1");
  });
});

describe("Propagations E1..E4", () => {
  it("E1 · ne modifie jamais le contenu d'un rapport validé (mention + v n+1)", () => {
    const fx = propagateArbitration({
      conceptId: "c1", unpublishedAnswers: ["a1", "a2"], publishedConclusionsAffected: ["k1"],
      validatedReport: "r4", arbitrationQueueItem: "w1", discoveriesAffected: ["d1", "d2"],
    });
    // Aucun set_state sur un rapport (le validé reste figé — R8).
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "report")).toBe(false);
    // Il prend la mention et une v n+1 est créée en brouillon.
    expect(has(fx, (e) => e.kind === "add_mention" && (e as any).report === "r4" && (e as any).mention === "newer_definition")).toBe(true);
    expect(has(fx, (e) => e.kind === "create" && (e as any).create === "report")).toBe(true);
    // Concept archivé + N+1 ; conclusions publiées dépassées (pas réécrites).
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "concept" && (e as any).to === "archived")).toBe(true);
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "conclusion" && (e as any).to === "superseded")).toBe(true);
    // Découvertes en revérification ; réponses non publiées recalculées.
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "discovery" && (e as any).to === "under_reverification")).toBe(true);
    expect(has(fx, (e) => e.kind === "recalc_in_place")).toBe(true);
  });

  it("E2 · part de « résolu » : l'incident finit archivé et l'élément de file traité", () => {
    const fx = propagateIncidentResolution({
      incidentId: "i1", recalculatedAnswers: ["a1"], reportsWithReserveMention: ["r1"], incidentQueueItem: "w9",
    });
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "incident" && (e as any).to === "archived")).toBe(true);
    expect(has(fx, (e) => e.kind === "remove_mention" && (e as any).report === "r1")).toBe(true);
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "queue_item" && (e as any).to === "processed")).toBe(true);
  });

  it("E3 · accès accordé n'exécute AUCUN recalcul avant le geste (Q3)", () => {
    const fx = propagateAccessGranted({ accessId: "x1", partialAnswers: ["a1", "a2"], requesterId: "u1" });
    expect(has(fx, (e) => e.kind === "recalc_in_place")).toBe(false); // Q3
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "answer" && (e as any).to === "resume_available")).toBe(true);
    expect(has(fx, (e) => e.kind === "notify")).toBe(true);
  });

  it("E4 · scan terminé recalcule automatiquement le périmètre partiel", () => {
    const fx = propagateScanCompleted({ partialAnswers: ["a1"], failedControls: ["ctl1"], stewardId: "s1" });
    expect(has(fx, (e) => e.kind === "set_state" && (e as any).ref?.kind === "answer" && (e as any).to === "running")).toBe(true);
    expect(has(fx, (e) => e.kind === "recalc_in_place")).toBe(true);
    expect(has(fx, (e) => e.kind === "create" && (e as any).create === "incident")).toBe(true);
  });
});
