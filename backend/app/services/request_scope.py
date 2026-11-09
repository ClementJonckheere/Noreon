"""Portée d'une demande vs répertoire réel du moteur — HONNÊTETÉ (Phase 1).

Le moteur hors-connexion sait faire une chose et une seule par réponse :
agréger/compter UNE mesure, éventuellement ventilée sur UNE dimension, et — en
mode approfondi — en tirer une tendance + attribution. Il ne sait PAS exécuter
une méthode analytique nommée (segmentation, RFM, cohortes, corrélation…), ni
croiser DEUX dimensions, ni fabriquer des intervalles dérivés (« par tranche »).

Plutôt que de substituer silencieusement une tendance de CA par défaut, on
DÉTECTE que la demande sort du répertoire et on le dit. On raisonne sur la
STRUCTURE de la demande (opérations, nombre de dimensions), pas sur une liste
d'entités métier : rien ici ne dépend de « produit », « âge » ou « magasin ».
Les libellés rendus à l'utilisateur CITENT ses propres mots.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


def _norm(s: str) -> str:
    return s.lower().translate(str.maketrans("àâäéèêëïîôöùûüç", "aaaeeeeiioouuuc"))


# Méthodes/OPÉRATIONS analytiques absentes du répertoire — jamais des entités
# métier. On cible l'ACTION (« segmenter », « une segmentation »), pas le nom
# d'une mesure ou d'une dimension : « le churn » ou « par segment » restent des
# analyses NORMALES (tendance/attribution sur une dimension existante).
_METHODS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brfm\b"), "une segmentation RFM"),
    # « segmentation », « segmente(r) » = action ; PAS « segment »/« par segment » (dimension).
    (re.compile(r"\bsegmentation\b|\bsegment(?:e|er|ez|ons|ent|erais?)\b"), "une segmentation"),
    (re.compile(r"\bscoring\b"), "un scoring"),
    (re.compile(r"\bclusteri|\bclusters?\b"), "un partitionnement (clustering)"),
    (re.compile(r"\bcohort"), "une analyse de cohortes"),
    (re.compile(r"\baffinit"), "une analyse d'affinité"),
    (re.compile(r"\bcorrelation"), "une corrélation"),
    (re.compile(r"\bregress"), "une régression"),
    (re.compile(r"\bprediction|\bprevision|\bforecast|\bpredire|\bmodele\s+predict"), "une prévision"),
    (re.compile(r"\b(ltv|clv)\b|valeur\s+vie"), "une valeur vie client"),
    (re.compile(r"\bfunnel\b|\bentonnoir\b"), "une analyse d'entonnoir"),
    (re.compile(r"\bquantile|\bquartile|\bdecile|\bpercentile"), "un découpage par quantiles"),
]

# Découpage DÉRIVÉ (binning) : « par tranche … », « classe/intervalle de … ».
# Le moteur agrège sur des dimensions EXISTANTES ; il ne crée pas d'intervalles.
# Robuste aux apostrophes droite/typographique et à l'absence d'apostrophe.
_BINNING = re.compile(
    r"\b(?:par\s+)?tranche[s]?\s+(?:d['’e]?\s*)?\w+"
    r"|\bclasse[s]?\s+(?:d['’e]?\s*)?\w+"
    r"|\bintervalle[s]?\s+(?:d['’e]?\s*)?\w+|\bbucket",
    re.IGNORECASE,
)

# Ventilation « par <dimension> ». On isole les dimensions NON temporelles : une
# seule → supporté (attribution) ; deux ou plus → croisement, hors répertoire.
_BY_DIM = re.compile(r"\bpar\s+(?:le|la|les|l'|un|une|des|du|de\s+la|de|d')?\s*([a-zà-ÿ_]{3,})", re.IGNORECASE)
_TEMPORAL = {"mois", "jour", "jours", "semaine", "semaines", "annee", "annees",
             "an", "ans", "trimestre", "trimestres", "date", "dates", "periode",
             "periodes", "temps", "an", "annee"}
_EXPLICIT_CROSS = re.compile(r"\bcrois|ventil", re.IGNORECASE)


@dataclass
class Objective:
    label: str          # libellé humain (cite les mots de l'utilisateur)
    status: str         # "supported" | "unsupported"
    reason: str = ""


@dataclass
class RequestScope:
    refuse: bool
    coverage: float                          # 0..1, couverture de la DEMANDE
    objectives: list[Objective] = field(default_factory=list)
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "refuse": self.refuse,
            "coverage": self.coverage,
            "objectives": [{"label": o.label, "status": o.status, "reason": o.reason}
                           for o in self.objectives],
            "message": self.message,
        }


def _crossed_dimensions(question: str) -> list[str]:
    """Dimensions non temporelles demandées en ventilation (dédupliquées)."""
    dims: list[str] = []
    for m in _BY_DIM.finditer(question):
        raw = m.group(1)
        if _norm(raw) in _TEMPORAL:
            continue
        if raw.lower() in {"quelle", "quel", "quels", "quelles", "chaque", "combien"}:
            continue
        if raw not in dims:
            dims.append(raw)
    return dims


def assess(question: str) -> RequestScope:
    """Confronte la demande au répertoire. `refuse=True` ⇒ le moteur doit
    l'expliquer au lieu de substituer une analyse."""
    q = question or ""
    nq = _norm(q)
    unsupported: list[Objective] = []

    seen: set[str] = set()
    for pat, label in _METHODS:
        if pat.search(nq) and label not in seen:
            seen.add(label)
            unsupported.append(Objective(label=label, status="unsupported",
                                         reason="méthode analytique hors répertoire"))
    # RFM subsume « segmentation » et « scoring » : on évite la liste redondante.
    if "une segmentation RFM" in seen:
        unsupported = [o for o in unsupported
                       if o.label not in ("une segmentation", "un scoring")]

    binning = _BINNING.search(q)
    if binning:
        phrase = binning.group(0).strip()
        unsupported.append(Objective(
            label=f"un découpage « {phrase} »", status="unsupported",
            reason="intervalles dérivés non calculés"))

    dims = _crossed_dimensions(q)
    if len(dims) >= 2 or (_EXPLICIT_CROSS.search(nq) and len(dims) >= 1):
        quoted = " × ".join(f"« {d} »" for d in dims[:3])
        unsupported.append(Objective(
            label=f"un croisement de dimensions ({quoted})", status="unsupported",
            reason="croisement multi-dimensions non supporté"))

    if not unsupported:
        # Rien d'hors-répertoire détecté : le pipeline normal peut répondre.
        return RequestScope(refuse=False, coverage=1.0, objectives=[], message="")

    # Au moins un objectif est hors répertoire : on REFUSE de substituer.
    # Couverture de la demande = 0 (aucun objectif réellement traité ici).
    labels = [o.label for o in unsupported]
    if len(labels) == 1:
        listed = labels[0]
        head = "Cette demande nécessite une analyse que le moteur actuel ne peut pas encore exécuter de manière fiable"
    else:
        listed = ", ".join(labels[:-1]) + " et " + labels[-1]
        head = "Cette demande nécessite plusieurs analyses que le moteur actuel ne peut pas encore exécuter de manière fiable"
    message = f"{head} : {listed}. Je préfère ne pas substituer une autre analyse."

    return RequestScope(refuse=True, coverage=0.0, objectives=unsupported, message=message)
