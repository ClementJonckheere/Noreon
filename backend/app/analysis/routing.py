"""Phase 2 — C3 : routage à deux modèles (audité, jamais silencieux).

- gpt-oss-120b (principal) traite TOUTE complexité ;
- gpt-oss-20b (simple) est réservé, par ALLOWLIST DÉTERMINISTE, aux demandes à un
  seul objectif `count` / `aggregate` / `ranking`, sans méthode, dépendance,
  ambiguïté, croisement ni relation non validée. **Tout doute → 120b.**

Escalade : si un plan produit par le 20b révèle une complexité inattendue, il est
REJETÉ puis relancé sur le 120b. L'escalade est explicite et auditée
(`selected_model`, `routing_reason`, `previous_model`, `escalation_reason`),
jamais silencieuse. Le routage de production reste désactivé tant que le
benchmark (C3) n'a pas tranché.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.analysis.contracts import Interpretation

SIMPLE_ALLOWED_TYPES = frozenset({"count", "aggregate", "ranking"})

# Signaux de COMPLEXITÉ au niveau de la question (conservateurs : au moindre
# doute on préfère le modèle principal). Réutilisés uniquement pour le PRÉ-routage
# — la décision ferme se fait sur le PLAN produit (allowlist ci-dessous).
_METHOD = re.compile(
    r"\b(rfm|segment|scoring|cluster|cohort|affinit|correlation|corrélation|"
    r"regress|prevision|prévision|prediction|prédiction|forecast|quantile|"
    r"quartile|decile|entonnoir|funnel)\w*", re.IGNORECASE)
_MULTI = re.compile(r"\bpuis\b|\bensuite\b|\bainsi que\b|;|,\s*(et|puis)\b|\bplusieurs\b", re.IGNORECASE)
_AMBIG = re.compile(r"\bht ou ttc\b|\bou\b\s*ttc|\?\s*\)|\(\s*ht", re.IGNORECASE)
_CROSS = re.compile(r"\bcrois|ventil|par\s+\w+\s+et\s+par\s+\w+", re.IGNORECASE)
_BINNING = re.compile(r"\btranche|\bclasse\s+d|\bintervalle\s+d", re.IGNORECASE)
_TREND = re.compile(r"\bevolu|évolu|\btendance|\bpourquoi|\bbaisse|\bhausse|\bchute|\brecul", re.IGNORECASE)
_SIMPLE_INTENT = re.compile(
    r"\bcombien\b|\bnombre d|\btotal\b|\bsomme\b|\bmoyen|\bclassement\b|\btop\b|\bcompte\b",
    re.IGNORECASE)


# Version de la LOGIQUE de routage (règles preroute + allowlist). À bumper à
# chaque changement de règle — la télémétrie shadow la persiste pour distinguer
# une dérive « routeur » d'une dérive « modèle/prompt/comparateur ».
ROUTER_VERSION = "1.0"


@dataclass(frozen=True)
class RoutingDecision:
    selected_model: str
    routing_reason: str
    previous_model: str | None = None
    escalation_reason: str | None = None
    matched_rule: str | None = None      # règle/allowlist ayant décidé (télémétrie)
    tier: str | None = None              # "simple" | "complex" (télémétrie)

    def as_dict(self) -> dict:
        return {
            "selected_model": self.selected_model,
            "routing_reason": self.routing_reason,
            "previous_model": self.previous_model,
            "escalation_reason": self.escalation_reason,
            "matched_rule": self.matched_rule,
            "tier": self.tier,
            "router_version": ROUTER_VERSION,
        }


def _complexity_signal(question: str) -> str | None:
    for name, pat in (("méthode", _METHOD), ("multi-objectifs", _MULTI),
                      ("ambiguïté", _AMBIG), ("croisement", _CROSS),
                      ("intervalles", _BINNING), ("tendance/causal", _TREND)):
        if pat.search(question or ""):
            return name
    return None


def preroute(question: str, *, main_model: str, simple_model: str) -> RoutingDecision:
    """Choix AVANT planification. Conservateur : seule une demande visiblement
    simple part au 20b ; tout signal de complexité ou tout doute → 120b."""
    signal = _complexity_signal(question)
    if signal is not None:
        return RoutingDecision(main_model, f"complexité détectée ({signal}) → modèle principal",
                               matched_rule=f"complexity:{signal}", tier="complex")
    if _SIMPLE_INTENT.search(question or ""):
        return RoutingDecision(simple_model, "demande simple (count/aggregate/ranking) → modèle simple",
                               matched_rule="simple_intent", tier="simple")
    return RoutingDecision(main_model, "doute → modèle principal par défaut",
                           matched_rule="default_doubt", tier="complex")


def plan_is_simple_eligible(interp: Interpretation) -> tuple[bool, str | None]:
    """Allowlist DÉTERMINISTE appliquée au PLAN. Renvoie (éligible, raison_refus).

    Note : la vérification « aucune relation non validée » est complétée par le
    CapabilityResolver (C6) avant toute exécution sur le 20b — s'il faut une
    jointure sans relation validée, on escalade également."""
    if len(interp.goals) != 1:
        return False, "plusieurs objectifs"
    g = interp.goals[0]
    if g.type not in SIMPLE_ALLOWED_TYPES:
        return False, f"type « {g.type} » hors allowlist"
    if g.depends_on:
        return False, "dépendance entre objectifs"
    if g.raw.get("method"):
        return False, "méthode analytique"
    if g.raw.get("ambiguities"):
        return False, "ambiguïté à lever"
    if g.entity_ref is None:
        return False, "entité non résolue"
    if interp.unresolved_terms:
        return False, "terme non résolu"
    if len(g.raw.get("dimensions") or []) > 1:
        return False, "croisement de dimensions"
    return True, None


def route_and_plan(question: str, catalog, *, plan_fn, main_model: str, simple_model: str):
    """Oriente puis planifie. `plan_fn(model, question, catalog) -> Interpretation`.

    Renvoie (Interpretation, RoutingDecision). Une planification 20b jugée trop
    complexe est REJETÉE et relancée sur le 120b, avec audit d'escalade."""
    decision = preroute(question, main_model=main_model, simple_model=simple_model)
    interp = plan_fn(decision.selected_model, question, catalog)

    if decision.selected_model == simple_model:
        ok, reason = plan_is_simple_eligible(interp)
        if not ok:
            previous = decision.selected_model
            interp = plan_fn(main_model, question, catalog)   # re-planification 120b
            decision = RoutingDecision(
                selected_model=main_model, routing_reason="escalade après plan 20b non éligible",
                previous_model=previous, escalation_reason=reason,
                matched_rule=f"escalation:{reason}", tier="complex")
    return interp, decision
