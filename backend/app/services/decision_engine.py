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

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionSet:
    intent: str = "exploration"
    intent_label: str = ""
    decisions: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _role_of(dimension: str) -> str | None:
    low = dimension.lower()
    for role, pat in _ROLE_HINTS.items():
        if re.search(pat, low):
            return role
    return None


def decide(*, question: str, metric_label: str, trend_direction: str | None,
           trend_pct: float | None, drivers: list[dict]) -> DecisionSet | None:
    """Produit des décisions adaptées au rôle à partir des facteurs dominants.

    `drivers` : [{dimension, segment, share}] issus du Reasoning Engine.
    """
    intent = detect_intent(question)
    ds = DecisionSet(intent=intent, intent_label=INTENT_LABEL.get(intent, intent))

    down = trend_direction == "baisse"
    pct_txt = f" ({trend_pct:+.0f}%)" if trend_pct else ""
    sens = "baisse" if down else "hausse"

    # Finance : présent quelle que soit l'analyse d'une mesure monétaire.
    if trend_direction in ("baisse", "hausse"):
        if down:
            ds.decisions.append(Decision(
                role="Directeur financier",
                priority=f"{metric_label} en {sens}{pct_txt} — préserver la marge et cadrer les coûts.",
                recommendation="Sécuriser la trésorerie, arbitrer les dépenses non essentielles, "
                               "réviser les prévisions.",
            ).as_dict())
        else:
            ds.decisions.append(Decision(
                role="Directeur financier",
                priority=f"{metric_label} en {sens}{pct_txt} — sécuriser et rentabiliser la dynamique.",
                recommendation="Vérifier que la hausse ne dégrade pas la marge ; réinvestir là où le "
                               "retour est prouvé.",
            ).as_dict())

    # Rôles métier selon le facteur dominant.
    seen_roles: set[str] = set()
    for d in drivers[:3]:
        role = _role_of(d.get("dimension", ""))
        if role is None or role in seen_roles:
            continue
        seen_roles.add(role)
        seg, share, dim = d.get("segment"), d.get("share", 0), d.get("dimension")
        if role == "reseau":
            ds.decisions.append(Decision(
                role="Directeur réseau",
                priority=f"« {seg} » concentre {share:.0f}% de la variation ({dim}).",
                recommendation=f"Auditer localement « {seg} » : conditions du point de vente, "
                               "concurrence, exécution terrain.",
            ).as_dict())
        elif role == "crm":
            ds.decisions.append(Decision(
                role="Responsable CRM",
                priority=f"Le segment client « {seg} » porte {share:.0f}% de la variation ({dim}).",
                recommendation=("Lancer une campagne de réactivation ciblée sur ce segment ; "
                                "mesurer l'effet sur la fréquence d'achat."),
            ).as_dict())
        elif role == "produit":
            ds.decisions.append(Decision(
                role="Directeur produit",
                priority=f"La gamme « {seg} » pèse {share:.0f}% de la variation ({dim}).",
                recommendation="Revoir l'assortiment et le prix de cette gamme ; vérifier les ruptures.",
            ).as_dict())
        elif role == "canal":
            ds.decisions.append(Decision(
                role="Responsable des opérations",
                priority=f"Le canal « {seg} » explique {share:.0f}% de la variation ({dim}).",
                recommendation="Analyser le parcours sur ce canal (friction, coût, conversion).",
            ).as_dict())

    if not ds.decisions:
        return None
    return ds
