"""Suggestion automatique de graphique (Module 9) — agent Reporting.

Le type de graphique est choisi selon la NATURE des données du résultat
(temporelle, catégorielle, distribution), l'utilisateur pouvant forcer un
autre type côté interface. En cas de données non graphables : repli sur le
tableau brut (comportement d'échec prévu par le cahier des charges).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")
_TEMPORAL_NAME = re.compile(r"(date|_at$|month|mois|jour|day|year|annee|week|semaine)", re.IGNORECASE)
# Les identifiants sont des CATÉGORIES, pas des mesures : un scatter sur
# store_id n'a aucun sens analytique.
_ID_NAME = re.compile(r"(^id$|_id$|^code|_code$)", re.IGNORECASE)


@dataclass
class ChartSuggestion:
    type: str  # line | bar | pie | histogram | scatter | table
    x: str | None = None
    y: list[str] = field(default_factory=list)
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "reason": self.reason,
            "alternatives": self.alternatives,
        }


def _is_number(v) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _is_temporal_value(v) -> bool:
    if isinstance(v, (datetime, date)):
        return True
    return isinstance(v, str) and bool(_DATE_RE.match(v.strip()))


def _classify(columns: list[str], rows: list[list]) -> dict[str, str]:
    """Classe chaque colonne : temporal | numeric | categorical | other."""
    kinds: dict[str, str] = {}
    sample = rows[:200]
    for i, col in enumerate(columns):
        values = [r[i] for r in sample if r[i] is not None]
        if not values:
            kinds[col] = "other"
            continue
        if all(_is_temporal_value(v) for v in values):
            kinds[col] = "temporal"
        elif all(_is_number(v) or _is_numeric_str(v) for v in values):
            if _ID_NAME.search(col):
                kinds[col] = "categorical"
            elif _TEMPORAL_NAME.search(col) and len(set(map(str, values))) > 2:
                # Un « nombre » nommé comme une date (year) reste temporel à l'axe.
                kinds[col] = "temporal"
            else:
                kinds[col] = "numeric"
        else:
            distinct = len({str(v) for v in values})
            kinds[col] = "categorical" if distinct <= max(30, len(values) // 2) else "other"
    return kinds


_CLEAN_NUMBER = re.compile(r"^-?\d+([.,]\d+)?$")


def _is_numeric_str(v) -> bool:
    # Un « nombre » textuel valide ne contient ni « + » (téléphone), ni espaces,
    # ni parenthèses : « +33600000001 » est un téléphone, pas une mesure.
    return isinstance(v, str) and bool(_CLEAN_NUMBER.match(v.strip()))


def _sorted_monotonic(values: list) -> bool:
    """True si la colonne est triée (asc ou desc) — signature d'une série
    agrégée (GROUP BY … ORDER BY), par opposition à un dump brut non ordonné."""
    keys = [str(v) for v in values]
    if len(keys) < 2:
        return True
    asc = all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1))
    desc = all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1))
    return asc or desc


def suggest_chart(columns: list[str], rows: list[list]) -> ChartSuggestion:
    if not columns or len(rows) < 2:
        return ChartSuggestion(type="table", reason="Trop peu de lignes pour un graphique.")

    kinds = _classify(columns, rows)
    temporal = [c for c in columns if kinds[c] == "temporal"]
    numeric = [c for c in columns if kinds[c] == "numeric"]
    categorical = [c for c in columns if kinds[c] == "categorical"]

    # Série temporelle → courbe, MAIS seulement si l'axe temps est ordonné
    # (série agrégée). Un dump brut non trié n'est pas une courbe.
    if temporal and numeric:
        tvals = [r[columns.index(temporal[0])] for r in rows]
        if _sorted_monotonic(tvals):
            return ChartSuggestion(
                type="line", x=temporal[0], y=numeric[:3],
                reason=f"Données temporelles ({temporal[0]}) : évolution en courbe.",
                alternatives=["bar", "table"],
            )

    # Catégories + mesure → barres (secteurs si peu de catégories).
    if categorical and numeric:
        n_cat = len({str(r[columns.index(categorical[0])]) for r in rows})
        alts = ["table"]
        if n_cat <= 8:
            alts = ["pie", "table"]
        return ChartSuggestion(
            type="bar", x=categorical[0], y=numeric[:3],
            reason=f"Données catégorielles ({categorical[0]}) : comparaison en barres.",
            alternatives=alts,
        )

    # Deux mesures → nuage de points.
    if len(numeric) >= 2 and not categorical and not temporal:
        return ChartSuggestion(
            type="scatter", x=numeric[0], y=[numeric[1]],
            reason="Deux mesures numériques : corrélation en nuage de points.",
            alternatives=["table"],
        )

    # Une seule mesure, beaucoup de lignes → histogramme de distribution.
    if len(numeric) == 1 and len(rows) >= 20:
        return ChartSuggestion(
            type="histogram", x=numeric[0], y=[numeric[0]],
            reason="Une mesure numérique : distribution en histogramme.",
            alternatives=["table"],
        )

    return ChartSuggestion(type="table", reason="Nature des données non graphable : tableau brut.")
