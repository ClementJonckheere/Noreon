#!/usr/bin/env python3
"""Challenge de l'analyste humain — mesurer la VALEUR de Noreon, pas seulement sa
justesse.

On ne compare plus « Noreon a-t-il la bonne réponse ? » mais « qu'apporte Noreon
face à un vrai Data Analyst ? ». Pour chaque scénario, une ligne de base humaine
écrite à la main (`demo/<scenario>/human_baseline.json` — ce qu'un analyste
compétent produit en ~45 min) est confrontée, critère par critère, à ce que Noreon
produit réellement (chronométré).

    cd backend && python ../demo/human_challenge.py retail

Le but n'est pas de « battre » l'humain : c'est de montrer la COMPLÉMENTARITÉ.
Noreon compresse la demi-journée d'analyse en secondes et ajoute la rigueur que
les humains sautent souvent (auto-critique, preuves traçables, reproductibilité,
projection prudente) ; l'humain garde l'avantage sur le contexte métier et le
jugement causal final.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _runner import SCENARIO_QUESTIONS, analyze, db_available  # noqa: E402

# (clé, libellé, « à qui l'avantage penche par nature »)
CRITERIA = [
    ("main_cause", "Cause principale"),
    ("secondary_causes", "Causes secondaires / signaux"),
    ("recommendations", "Recommandations actionnables"),
    ("projection", "Projection « et si rien ne change »"),
    ("self_critique", "Auto-critique (ce qui invaliderait)"),
    ("evidence_trail", "Traçabilité (SQL, sources, preuves)"),
    ("reproducible", "Reproductibilité à l'identique"),
    ("business_context", "Contexte métier / causalité terrain"),
]


def _noreon_profile(r, inv, seconds) -> dict:
    """Projette la réponse Noreon sur les mêmes critères que l'analyste."""
    decisions = (r.decisions or {}).get("decisions") if r.decisions else None
    concluded = bool((inv.get("attribution") or inv.get("multi_causes")
                      or inv.get("broad_based") or inv.get("seasonal")
                      or inv.get("low_quality")))
    steps = inv.get("steps", [])
    has_sql = any("select" in (s.get("sql") or "").lower() for s in steps)
    return {
        "main_cause": concluded,
        "secondary_causes": bool(inv.get("multi_causes")
                                 or len(inv.get("drivers_struct") or []) >= 2
                                 or r.serendipity),
        "recommendations": bool(decisions),
        "projection": bool(r.decisions and (r.decisions or {}).get("inaction")),
        "self_critique": bool(r.self_critique),
        "evidence_trail": has_sql or bool(r.sources),
        "reproducible": True,                 # déterministe, rejouable à l'identique
        "business_context": False,            # corrélations, pas causalité terrain
        "time_label": f"~{seconds:.0f} s",
    }


def _mark(v) -> str:
    return "✅" if v else "❌"


def run(scenario: str) -> None:
    base_path = HERE / scenario / "human_baseline.json"
    if not base_path.exists():
        print(f"Pas de ligne de base humaine pour « {scenario} » "
              f"({base_path.relative_to(HERE.parent)}).")
        return
    human = json.loads(base_path.read_text(encoding="utf-8"))
    question = human.get("question") or SCENARIO_QUESTIONS.get(scenario, "")

    if not db_available(scenario):
        print(f"Base noreon_demo_{scenario} injoignable — lancer setup_scenario.sh {scenario}.")
        return

    t0 = perf_counter()
    r, _ = analyze(scenario, question)
    seconds = perf_counter() - t0
    noreon = _noreon_profile(r, r.investigation or {}, seconds)

    print("\n" + "═" * 72)
    print(f" CHALLENGE DE L'ANALYSTE HUMAIN — {scenario}")
    print("═" * 72)
    print(f" Question : {question}\n")
    print(f" {'Critère':<38}{'Analyste':<12}{'Noreon'}")
    print(f" {'-' * 38}{'-' * 12}{'-' * 8}")
    for key, label in CRITERIA:
        print(f" {label:<38}{_mark(human.get(key)):<12}{_mark(noreon.get(key))}")
    print(f" {'Temps':<38}{human.get('time_label', '~45 min'):<12}{noreon['time_label']}")

    # Synthèse de valeur : avantages nets de chaque côté.
    noreon_plus = [label for key, label in CRITERIA
                   if noreon.get(key) and not human.get(key)]
    human_plus = [label for key, label in CRITERIA
                  if human.get(key) and not noreon.get(key)]
    print("\n Ce que Noreon ajoute :")
    for x in noreon_plus + [f"Temps : {noreon['time_label']} vs {human.get('time_label', '~45 min')}"]:
        print(f"   + {x}")
    if human_plus:
        print("\n Ce qui reste à l'humain :")
        for x in human_plus:
            print(f"   • {x}")
    print("\n → " + human.get("verdict", "Complémentaires : Noreon fait le travail de fond en "
                               "secondes, l'humain tranche le jugement métier."))


def main(argv: list[str]) -> int:
    scenarios = argv or ["retail"]
    for sc in scenarios:
        run(sc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
