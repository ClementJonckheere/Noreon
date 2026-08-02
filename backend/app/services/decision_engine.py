"""Decision Engine — des mêmes données, des décisions selon le RÔLE.

Le Reasoning Engine explique CE QUI se passe. Le Decision Engine répond à
« que ferait un directeur financier / un responsable CRM / un directeur réseau ? ».
Les données sont identiques ; les priorités changent selon le métier.

    CA -12 %  →  Finance : préserver la marge, contrôler les coûts.
              →  CRM     : réactiver les clients fidèles en repli.
              →  Réseau  : 3 magasins pèsent 65 % de la baisse → audit local.

Tout est déterministe, dérivé des facteurs dominants réels de l'analyse.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

# Vocabulaire d'un axe d'analyse → rôle le plus concerné.
_ROLE_HINTS = {
    "reseau": r"magasin|store|shop|boutique|ville|city|region|région|zone|secteur|territoire",
    "crm": r"client|customer|fidel|fidél|loyal|age\b|âge|genre|segment client|acheteur",
    "produit": r"produit|product|categor|catégor|gamme|article|référence|sku",
    "canal": r"paiement|payment|canal|channel|method|mode",
}

# Intentions détectables derrière une question.
_INTENTS = [
    ("diagnostic", r"pourquoi|cause|expliqu|analyse|problème|probleme|baisse|chute|anomal"),
    ("comparaison", r"compar|versus|\bvs\b|par magasin|par région|par region|classement|meilleur|top\b"),
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
    role: str            # libellé du rôle
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


def _role_of(dimension: str) -> str | None:
    low = dimension.lower()
    for role, pat in _ROLE_HINTS.items():
        if re.search(pat, low):
            return role
    return None


# role → (libellé, action, justification, effort typique de l'action)
_ROLE_ACTIONS = {
    "crm": ("Responsable CRM",
            "Lancer une campagne de réactivation ciblée sur « {seg} » ; "
            "mesurer l'effet sur la fréquence d'achat.",
            "le segment client « {seg} » porte {share:.0f}% de la variation ({dim}).",
            "Faible"),
    "reseau": ("Directeur réseau",
               "Auditer localement « {seg} » : conditions du point de vente, "
               "concurrence, exécution terrain.",
               "{share:.0f}% de la variation provient de « {seg} » ({dim}).",
               "Moyen"),
    "produit": ("Directeur produit",
                "Revoir l'assortiment et le prix de la gamme « {seg} » ; vérifier les ruptures.",
                "la gamme « {seg} » pèse {share:.0f}% de la variation ({dim}).",
                "Élevé"),
    "canal": ("Responsable des opérations",
              "Analyser le parcours sur le canal « {seg} » (friction, coût, conversion).",
              "le canal « {seg} » explique {share:.0f}% de la variation ({dim}).",
              "Moyen"),
}

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
           history: Callable[[str, str], str | None] | None = None) -> DecisionSet | None:
    """Produit des décisions adaptées au rôle à partir des facteurs dominants.

    `drivers` : [{dimension, segment, share}] issus du Reasoning Engine.
    `history(role, recommendation) -> str | None` : annotation de mémoire métier
    (« déjà appliquée avec succès… ») si une reco proche a déjà été qualifiée.
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

    # Finance : présent quelle que soit l'analyse d'une mesure monétaire.
    if trend_direction in ("baisse", "hausse"):
        just = (f"parce que {metric_label} évolue de {trend_pct:+.0f}%, "
                "ce qui pèse directement sur la marge." if trend_pct
                else f"parce que {metric_label} est orienté à la {sens}.")
        fin_impact = "Élevé" if trend_pct and abs(trend_pct) >= 10 else "Moyen"
        if down:
            ds.decisions.append(Decision(
                role="Directeur financier",
                priority=f"{metric_label} en {sens}{pct_txt} — préserver la marge et cadrer les coûts.",
                recommendation="Sécuriser la trésorerie, arbitrer les dépenses non essentielles, "
                               "réviser les prévisions.",
                justification=just, effort="Moyen", impact_level=fin_impact,
                stars=_stars(fin_impact, "Moyen"),
            ).as_dict())
        else:
            ds.decisions.append(Decision(
                role="Directeur financier",
                priority=f"{metric_label} en {sens}{pct_txt} — sécuriser et rentabiliser la dynamique.",
                recommendation="Vérifier que la hausse ne dégrade pas la marge ; réinvestir là où le "
                               "retour est prouvé.",
                justification=just, effort="Moyen", impact_level=fin_impact,
                stars=_stars(fin_impact, "Moyen"),
            ).as_dict())

    # Rôles métier selon le facteur dominant (impact + justification + priorité).
    seen_roles: set[str] = set()
    for d in drivers[:3]:
        role = _role_of(d.get("dimension", ""))
        if role is None or role in seen_roles or role not in _ROLE_ACTIONS:
            continue
        seen_roles.add(role)
        seg, share, dim = d.get("segment"), d.get("share", 0), _clean_dimension(d.get("dimension"))
        role_label, action_tpl, just_tpl, effort = _ROLE_ACTIONS[role]
        impact, conf, impact_level = _estimate_impact(share, trend_pct)
        ds.decisions.append(Decision(
            role=role_label,
            priority=f"« {seg} » concentre {share:.0f}% de la variation ({dim}).",
            recommendation=action_tpl.format(seg=seg, dim=dim),
            justification="parce que " + just_tpl.format(seg=seg, dim=dim, share=share),
            impact=impact, impact_confidence=conf,
            effort=effort, impact_level=impact_level, stars=_stars(impact_level, effort),
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
