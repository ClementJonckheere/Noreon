"""Chronologie narrée — raconter une tendance dans le temps.

Beaucoup d'outils affichent une courbe ; peu la **racontent**. À partir d'une
série temporelle (période, valeur), Noreon repère la dynamique récente et la met
en mots :

    « Cette tendance dure depuis 4 mois : le CA recule de mars (stable) à
      juillet (-11 %). »

Tout est calculé hors-ligne, sans rien inventer : on lit la série réelle.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_PERIOD_RE = re.compile(r"^\d{4}[-/](\d{2}|Q[1-4]|W\d{1,2})")  # 2025-01, 2025/Q1, 2025-W03


@dataclass
class Chronicle:
    periods: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    direction: str = "stable"       # hausse | baisse | stable
    streak: int = 0                 # nb de périodes consécutives dans le même sens (fin de série)
    total_pct: float = 0.0          # variation début → fin
    narrative: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _looks_temporal(value) -> bool:
    s = str(value)
    return bool(_PERIOD_RE.match(s)) or bool(re.match(r"^\d{4}-\d{2}-\d{2}", s))


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(columns: list[str], rows: list[list], *, metric_label: str = "la mesure") -> Chronicle | None:
    """Construit une chronologie si la série a l'allure d'un historique temporel."""
    if not rows or len(columns) < 2 or len(rows) < 3:
        return None
    # La première colonne doit ressembler à une période.
    if not all(_looks_temporal(r[0]) for r in rows[:3]):
        return None
    series = [(str(r[0]), _num(r[1])) for r in rows if _num(r[1]) is not None]
    if len(series) < 3:
        return None

    periods = [p for p, _ in series]
    values = [v for _, v in series]

    # Streak terminal : nb de pas consécutifs de même signe, en partant de la fin.
    def sign(a: float, b: float) -> int:
        if b > a * 1.001:
            return 1
        if b < a * 0.999:
            return -1
        return 0

    signs = [sign(values[i - 1], values[i]) for i in range(1, len(values))]
    streak = 0
    last_dir = 0
    for s in reversed(signs):
        if s == 0:
            break
        if last_dir == 0:
            last_dir = s
            streak = 1
        elif s == last_dir:
            streak += 1
        else:
            break

    first, last = values[0], values[-1]
    total_pct = ((last - first) / first * 100) if first else 0.0
    direction = "hausse" if last_dir > 0 else "baisse" if last_dir < 0 else "stable"

    ch = Chronicle(
        periods=periods, values=[round(v, 2) for v in values],
        direction=direction, streak=streak, total_pct=round(total_pct, 1),
    )
    ch.narrative = _narrate(ch, metric_label)
    return ch


def _narrate(ch: Chronicle, metric_label: str) -> str:
    if ch.streak >= 2:
        sens = "recule" if ch.direction == "baisse" else "progresse"
        lead = (f"Cette tendance dure depuis {ch.streak} période(s) consécutive(s) : "
                f"{metric_label} {sens} de {ch.periods[-ch.streak - 1]} à {ch.periods[-1]}")
        if ch.total_pct:
            lead += f" ({ch.total_pct:+.0f}% sur l'ensemble de la période)"
        return lead + "."
    if ch.direction == "stable":
        return f"{metric_label} est globalement stable sur la période observée."
    sens = "en baisse" if ch.direction == "baisse" else "en hausse"
    return f"{metric_label} est {sens} sur la dernière période ({ch.total_pct:+.0f}% au total)."
