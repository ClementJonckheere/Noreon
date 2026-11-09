"""Decision Engine — des mêmes données, des recommandations d'action.

Le Reasoning Engine explique CE QUI se passe ; le Decision Engine propose QUOI
faire. Il ne présume d'aucune organisation : il reçoit un `BusinessContext` (qui
peut être vide) et l'utilise pour PERSONNALISER, jamais pour fonctionner.

    Finding (facteur dominant)
      → le contexte connaît-il un décideur pour ce concept ?
        → oui : recommandation attribuée à ce rôle (personnalisation)
        → non : recommandation GÉNÉRIQUE (« une action possible consiste à… »)

Un entrepreneur solo (contexte vide) obtient donc des recommandations utiles et
mesurables, sans qu'aucun rôle d'organisation ne soit jamais requis. Tout reste
déterministe, dérivé des facteurs dominants réels de l'analyse.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from app.services import responsibility
from app.services.business_context import EMPTY, BusinessContext

# Intentions détectables derrière une question (vocabulaire neutre, sans domaine).
_INTENTS = [
    ("diagnostic", r"pourquoi|cause|expliqu|analyse|problème|probleme|baisse|chute|anomal"),
    ("comparaison", r"compar|versus|\bvs\b|classement|meilleur|top\b"),
    ("reporting", r"rapport|bilan|mensuel|trimestriel|comité|comite|présentation|presentation|synthèse|synthese"),
    ("suivi", r"évolu|evolu|tendance|suivi|historique|dans le temps|par mois"),
]


def detect_intent(question: str) -> str:
    q = question.lower()
    for name, pat in _INTENTS:
        if re.search(pat, q):
            return name
    return "exploration"


INTENT_LABEL = {
    "diagnostic": "Diagnostiquer un problème",
    "comparaison": "Comparer des entités",
    "reporting": "Préparer un rapport / comité",
    "suivi": "Suivre une évolution",
    "exploration": "Explorer les données",
}


@dataclass
class Decision:
    role: str            # libellé du rôle — VIDE si l'organisation est inconnue
    priority: str        # phrase de priorité
    recommendation: str  # action concrète
    justification: str = ""          # « pourquoi cette recommandation ? » (Decision Journal)
    impact: str | None = None        # fourchette d'impact estimé (ex. « +4 à +7 % »)
    impact_confidence: str | None = None  # Faible | Moyenne | Élevée
    effort: str = "Moyen"            # Faible | Moyen | Élevé
    impact_level: str = "Moyen"      # Faible | Moyen | Élevé (pour la matrice)
    stars: int = 3                   # priorité rapport effort/impact (1..5)
    history: str | None = None       # mémoire métier (« déjà appliquée avec succès… »)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionSet:
    intent: str = "exploration"
    intent_label: str = ""
    restated: str = ""               # objectif reformulé (« Diagnostiquer une baisse des ventes »)
    decisions: list[dict] = field(default_factory=list)
    inaction: str | None = None      # « et si je ne fais rien ? » (projection prudente)

    def as_dict(self) -> dict:
        return asdict(self)


def restate_intent(question: str, *, intent: str | None = None,
                   metric_label: str | None = None, trend_direction: str | None = None,
                   top_dimension: str | None = None) -> str:
    """Reformule l'objectif réel — pas seulement la catégorie.

    « diagnostic » → « Diagnostiquer une baisse des ventes ». Le moteur montre
    qu'il a compris la demande."""
    intent = intent or detect_intent(question)
    metric = _clean_metric(metric_label)
    dim = _clean_dimension(top_dimension)
    if intent == "diagnostic":
        if trend_direction == "baisse":
            return f"Diagnostiquer une baisse de {metric}"
        if trend_direction == "hausse":
            return f"Comprendre une hausse de {metric}"
        return f"Diagnostiquer l'évolution de {metric}"
    if intent == "comparaison":
        return f"Comparer les performances par {dim}" if dim else f"Comparer {metric}"
    if intent == "reporting":
        return f"Préparer un rapport sur {metric}"
    if intent == "suivi":
        return f"Suivre l'évolution de {metric}"
    return f"Explorer {metric}"


def _clean_metric(label: str | None) -> str:
    if not label:
        return "l'indicateur"
    m = re.sub(r"^(total de|effectif de)\s*", "", label).strip()
    m = re.sub(r"\s*\(nombre de lignes\)", "", m)
    return m or "l'indicateur"


def _clean_dimension(label: str | None) -> str:
    if not label:
        return ""
    return re.sub(r"\s*\([^)]*\)", "", label).strip()


_EFFORT_RANK = {"Faible": 1, "Moyen": 2, "Élevé": 3}
_IMPACT_RANK = {"Faible": 1, "Moyen": 2, "Élevé": 3}


def _estimate_impact(share: float, trend_pct: float | None) -> tuple[str | None, str | None, str]:
    """Fourchette d'impact récupérable estimée + confiance + niveau, à partir de la
    part du facteur dans la variation. Volontairement prudente (jamais une promesse)."""
    if not trend_pct:
        return None, None, "Faible"
    addressable = share / 100.0 * abs(trend_pct)   # part de la variation portée par ce facteur
    low, high = addressable * 0.3, addressable * 0.6  # récupération partielle réaliste
    level = "Élevé" if addressable >= 6 else "Moyen" if addressable >= 3 else "Faible"
    # Plafond de crédibilité : au-delà, une « fourchette d'impact » cesse d'être
    # crédible. On ne promet jamais plus qu'un redressement partiel raisonnable.
    low, high = min(low, 25.0), min(high, 45.0)
    if high < 0.5:
        return None, None, level
    conf = "Moyenne" if share >= 45 else "Faible"
    return f"+{low:.0f} à +{high:.0f} %", conf, level


def _stars(impact_level: str, effort: str) -> int:
    """Priorité selon le rapport effort/impact (fort impact + faible effort = 5)."""
    return max(1, min(5, 3 + _IMPACT_RANK.get(impact_level, 2) - _EFFORT_RANK.get(effort, 2)))


def decide(*, question: str, metric_label: str, trend_direction: str | None,
           trend_pct: float | None, drivers: list[dict],
           recent_rate: float | None = None,
           history: Callable[[str, str], str | None] | None = None,
           context: BusinessContext = EMPTY) -> DecisionSet | None:
    """Produit des recommandations à partir des facteurs dominants.

    `drivers` : [{dimension, segment, share}] issus du Reasoning Engine.
    `context` : `BusinessContext` (éventuellement vide). Il PERSONNALISE les
    recommandations par rôle quand l'organisation est connue ; sans lui, les
    recommandations restent génériques et parfaitement utilisables.
    `history(role, recommendation) -> str | None` : annotation de mémoire métier.
    """
    intent = detect_intent(question)
    top_dim = drivers[0].get("dimension") if drivers else None
    ds = DecisionSet(
        intent=intent, intent_label=INTENT_LABEL.get(intent, intent),
        restated=restate_intent(question, intent=intent, metric_label=metric_label,
                                trend_direction=trend_direction, top_dimension=top_dim),
    )

    down = trend_direction == "baisse"
    pct_txt = f" ({trend_pct:+.0f}%)" if trend_pct else ""
    sens = "baisse" if down else "hausse"

    # Cadrage financier : pertinent pour toute mesure monétaire. Attribué à un
    # décideur SI le contexte en déclare un ; sinon générique (aucune organisation
    # n'est présumée). Noreon ne recommande PAS d'actions marge/trésorerie tant que
    # ces mesures ne sont pas dans l'analyse : il cadre au périmètre diagnostiqué.
    if trend_direction in ("baisse", "hausse"):
        fin_role = context.actor("finance") or ""
        just = (f"parce que {metric_label} évolue de {trend_pct:+.0f}%, mais l'effet sur "
                "la rentabilité dépend de données de marge/coûts absentes de ce diagnostic."
                if trend_pct
                else f"parce que {metric_label} est orienté à la {sens} ; l'impact marge n'est pas couvert ici.")
        fin_impact = "Élevé" if trend_pct and abs(trend_pct) >= 10 else "Moyen"
        if down:
            ds.decisions.append(Decision(
                role=fin_role,
                priority=f"{metric_label} en {sens}{pct_txt} — cadrer l'impact avant tout arbitrage.",
                recommendation=(f"Réviser les prévisions de {metric_label} sur le périmètre concerné. "
                                "L'effet sur la marge et la trésorerie n'est pas quantifiable ici : ces "
                                "mesures ne font pas partie de l'analyse."),
                justification=just, effort="Moyen", impact_level=fin_impact,
                stars=_stars(fin_impact, "Moyen"),
            ).as_dict())
        else:
            ds.decisions.append(Decision(
                role=fin_role,
                priority=f"{metric_label} en {sens}{pct_txt} — confirmer la rentabilité avant d'investir.",
                recommendation=(f"Vérifier que la dynamique de {metric_label} se traduit en rentabilité "
                                "avant réinvestissement : l'effet sur la marge n'est pas mesuré par cette analyse."),
                justification=just, effort="Moyen", impact_level=fin_impact,
                stars=_stars(fin_impact, "Moyen"),
            ).as_dict())

    # Facteurs dominants → recommandation. Le PREMIER facteur est la cause
    # principale : sa décision est rehaussée d'une étoile pour mener la liste.
    #
    # On demande au BusinessContext s'il connaît un décideur pour ce facteur. Si
    # oui → recommandation attribuée (personnalisation). Si non → recommandation
    # GÉNÉRIQUE : c'est cette branche qui rend Noreon utilisable par un entrepreneur
    # seul, sans aucune organisation déclarée.
    seen: set[str] = set()
    for idx, d in enumerate(drivers[:3]):
        seg, share = d.get("segment"), d.get("share", 0)
        resp = responsibility.resolve(context, d.get("dimension", ""), seg, d.get("samples") or [])
        if resp is not None and not resp.action_template:
            continue  # concept reconnu mais sans action dédiée (p. ex. le temps)

        if resp is not None:  # décideur connu → personnalisation
            key = resp.actor_label or resp.concept_key
            if key in seen:
                continue
            seen.add(key)
            dim = resp.concept_label
            role_label, effort = (resp.actor_label or ""), resp.effort
            recommendation = resp.action_template.format(seg=seg, dim=dim, share=share)
            justification = "parce que " + resp.justification_template.format(seg=seg, dim=dim, share=share)
        else:                 # aucun responsable connu → recommandation générique
            dim = _clean_dimension(d.get("dimension", "")) or "ce facteur"
            key = f"generic:{dim}:{seg}"
            if key in seen:
                continue
            seen.add(key)
            role_label, effort = "", "Moyen"
            recommendation = (f"Une action possible : cibler « {seg} » — le facteur qui concentre le "
                              f"plus la variation — et tester un levier dédié. L'effet pourra être "
                              f"mesuré sur {_clean_metric(metric_label)}.")
            justification = f"parce que « {seg} » concentre {share:.0f}% de la variation observée ({dim})."

        impact, conf, impact_level = _estimate_impact(share, trend_pct)
        stars = _stars(impact_level, effort)
        if idx == 0:  # cause principale de la variation
            stars = min(5, stars + 1)
        ds.decisions.append(Decision(
            role=role_label,
            priority=f"« {seg} » concentre {share:.0f}% de la variation ({dim}).",
            recommendation=recommendation, justification=justification,
            impact=impact, impact_confidence=conf,
            effort=effort, impact_level=impact_level, stars=stars,
        ).as_dict())

    # Mémoire métier : annoter les recommandations déjà retenues / éprouvées.
    if history is not None:
        for dec in ds.decisions:
            dec["history"] = history(dec.get("role", ""), dec.get("recommendation", ""))

    # Priorité rapport effort/impact d'abord : le décideur choisit selon le coût/bénéfice.
    ds.decisions.sort(key=lambda x: -x.get("stars", 3))

    if not ds.decisions:
        return None

    # « Et si je ne fais rien ? » — projection PRUDENTE si la baisse se poursuit.
    if down and recent_rate and recent_rate < -0.5:
        horizon = 3
        factor = (1 + recent_rate / 100.0) ** horizon
        add_decline = (1 - factor) * 100
        if add_decline >= 1:
            ds.inaction = (
                "Si la tendance observée se maintient et qu'aucun changement majeur n'intervient, "
                f"{metric_label} pourrait reculer d'environ {add_decline:.0f}% supplémentaires "
                f"sur les {horizon} prochaines périodes. Il s'agit d'une projection sous hypothèses, "
                "pas d'une prédiction."
            )
    return ds
