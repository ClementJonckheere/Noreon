#!/usr/bin/env python3
"""Framework de non-régression — Gold Standard → Noreon → écart → score.

Pour chaque scénario, on compare la sortie RÉELLE du moteur à la vérité attendue
(`demo/<scenario>/expected.json`, projection machine-vérifiable du Gold Standard)
et on produit un **bulletin** noté sur 100. Utilisable en CI : sortie non nulle si
un scénario passe sous le seuil.

    cd backend && python ../demo/benchmark.py            # tous les scénarios
    cd backend && python ../demo/benchmark.py retail crm # ciblés
    cd backend && python ../demo/benchmark.py --threshold 90

Chaque scénario dont la base source est injoignable est marqué SKIP (non compté).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _runner import SCENARIO_QUESTIONS, analyze, db_available  # noqa: E402

HERE = Path(__file__).resolve().parent
PASS_THRESHOLD = 80  # score minimal pour valider un scénario

# Barème : (clé, libellé, poids). Total = 100.
RUBRIC = [
    ("intent", "Intention comprise", 10),
    ("trend", "Sens de la variation", 15),
    ("attr_dim", "Bon axe causal", 25),
    ("attr_seg", "Bon segment", 25),
    ("attr_contrib", "Contribution suffisante", 15),
    ("role", "Bon décideur (★≥4)", 10),
]


def _norm(s) -> str:
    return str(s or "").lower()


def _extract(r) -> dict:
    """Projette la réponse Noreon sur les champs vérifiables."""
    inv = r.investigation or {}
    attr = inv.get("attribution") or {}
    return {
        "intent": _norm(r.intent),
        "trend": _norm((r.chronicle or {}).get("direction")),
        "attr_dim": _norm(attr.get("dimension")),
        "attr_seg": _norm(attr.get("segment")),
        "attr_contrib": attr.get("contribution_pct"),
        "decisions": (r.decisions or {}).get("decisions", []),
    }


def _score(got: dict, exp: dict) -> list[tuple]:
    """Renvoie [(clé, libellé, poids, ok, détail)] pour chaque critère du barème."""
    a = exp["attribution"]
    checks = {
        "intent": (got["intent"] == exp["intent"], f"{got['intent'] or '—'}"),
        "trend": (got["trend"] == _norm(exp["trend_direction"]), f"{got['trend'] or '—'}"),
        "attr_dim": (_norm(a["dimension_contains"]) in got["attr_dim"],
                     got["attr_dim"] or "—"),
        "attr_seg": (_norm(a["segment_contains"]) in got["attr_seg"],
                     got["attr_seg"] or "—"),
        "attr_contrib": (isinstance(got["attr_contrib"], (int, float))
                         and got["attr_contrib"] >= a["min_contribution_pct"],
                         f"{got['attr_contrib']}%" if got["attr_contrib"] is not None else "—"),
        "role": _role_ok(got["decisions"], exp["lead_role"]),
    }
    return [(k, lbl, w, checks[k][0], checks[k][1]) for k, lbl, w in RUBRIC]


def _role_ok(decisions: list, expected_role: str) -> tuple[bool, str]:
    for d in decisions:
        if _norm(expected_role) in _norm(d.get("role")) and d.get("stars", 0) >= 4:
            return True, f"{d['role']} ({d.get('stars')}★)"
    top = decisions[0]["role"] if decisions else "—"
    return False, f"attendu « {expected_role} » ; en tête : {top}"


# --- Scorecard du RAISONNEMENT (pas seulement la réponse) --------------------
# Note la DÉMARCHE : si demain le moteur de raisonnement change, on voit OÙ il se
# dégrade. Proxies déterministes, volontairement simples et transparents.
def _stars(n: int) -> str:
    n = max(1, min(5, n))
    return "★" * n + "☆" * (5 - n)


def reasoning_scorecard(r) -> list[tuple[str, int, str]]:
    inv = r.investigation or {}
    steps = inv.get("steps", [])
    analyses = len(steps)
    has_trend = any("Tendance" in s.get("title", "") for s in steps)
    has_attr = any("Attribution" in s.get("title", "") for s in steps)
    measure_ok = "effectif" not in _norm(inv.get("metric_label"))
    decided = (r.decisions or {}).get("decisions", [])
    justified = any(d.get("justification") for d in decided)
    explained = bool(r.self_critique) and bool(inv.get("conclusion"))
    # Efficacité : trouver la réponse en peu d'analyses (proxy : nb d'étapes).
    eff = 5 if analyses <= 6 else 4 if analyses <= 8 else 3

    return [
        ("Plan", 5 if (has_trend and has_attr) else 3,
         f"tendance+attribution" if has_trend and has_attr else "incomplet"),
        ("Choix des dimensions", 5 if analyses >= 3 else max(2, analyses),
         f"{analyses} axes explorés"),
        ("Mesure retenue", 5 if measure_ok else 3, inv.get("metric_label", "—")),
        ("Explication", 5 if explained else 3,
         "conclusion + auto-critique" if explained else "partielle"),
        ("Décision", 5 if justified else 3,
         "justifiée" if justified else "sans justification"),
        ("Efficacité", eff, f"{analyses} analyses"),
    ]


def _print_reasoning(r) -> None:
    print("    · Raisonnement :")
    for label, stars, detail in reasoning_scorecard(r):
        print(f"        {_stars(stars)}  {label:<22} {detail}")


# --- Section CHALLENGE : cas conçus pour CASSER le moteur --------------------
def discover_challenges() -> list[str]:
    root = HERE / "challenge"
    if not root.is_dir():
        return []
    return sorted(f"challenge/{p.name}" for p in root.iterdir()
                  if (p / "expected.json").exists())


def run_challenge(sc: str) -> None:
    exp = json.loads((HERE / sc / "expected.json").read_text(encoding="utf-8"))
    name = sc.split("/", 1)[1]
    if not db_available(sc):
        print(f"\n▹ {name:<18} SKIP — base injoignable (setup_scenario.sh {sc}).")
        return
    r, _ = analyze(sc, exp["question"])
    inv = r.investigation or {}
    attr = inv.get("attribution") or {}
    learned = None
    notes: list[str] = []

    if exp.get("expects_low_quality"):
        # Humilité : s'abstenir sur données trop trouées (pas de fausse certitude).
        low_q = bool(inv.get("low_quality"))
        no_decision = (r.decisions is None) or not (r.decisions or {}).get("decisions")
        says_cannot = "conclure" in (inv.get("conclusion") or "").lower()
        learned = low_q and no_decision and says_cannot
        notes.append(f"abstention honnête : {'✓' if (low_q and says_cannot) else '✗'}")
        notes.append(f"aucune décision : {'✓' if no_decision else '✗'}")
    elif exp.get("expects_seasonal"):
        # Saisonnalité : reconnaître que la baisse est un creux annuel (pas d'anomalie)
        # et NE recommander aucune action corrective.
        seasonal = bool(inv.get("seasonal"))
        no_decision = (r.decisions is None) or not (r.decisions or {}).get("decisions")
        learned = seasonal and no_decision
        notes.append(f"baisse reconnue saisonnière : {'✓' if seasonal else '✗'}")
        notes.append(f"aucune action corrective : {'✓' if no_decision else '✗'}")
    elif exp.get("expects_no_dominant_cause"):
        # Cause diffuse : reconnaître qu'AUCUN segment ne se détache (pas de tautologie).
        learned = bool(inv.get("broad_based")) and inv.get("attribution") is None \
            and not inv.get("drivers_struct")
    elif "multi_cause" in exp:
        # Causes multiples : nommer plusieurs foyers, pas un seul (ni « généralisée »).
        mc = exp["multi_cause"]
        causes = inv.get("multi_causes") or []
        cum = sum(c.get("contribution_pct", 0) for c in causes)
        accepted = [_norm(s) for s in mc.get("segments_any", [])]
        named_ok = all(any(a in _norm(c.get("segment")) for a in accepted) for c in causes) \
            if accepted else True
        learned = (len(causes) >= mc.get("min_causes", 2)
                   and cum >= mc.get("cumulative_min_pct", 0) and named_ok)
        listed = ", ".join(f"{c['segment']} ({c['contribution_pct']:.0f}%)" for c in causes)
        notes.append(f"foyers nommés : {'✓' if learned else '✗'} "
                     f"[{listed or '—'}] (cumul {cum:.0f}%)")
    elif "robustness" in exp:
        # Colonnes opaques : retrouver la mesure PAR LES DONNÉES et la cause PAR LA VALEUR.
        rob = exp["robustness"]
        measure_ok = "effectif" not in _norm(inv.get("metric_label"))
        seg_ok = _norm(rob.get("segment_contains", "")) in _norm(attr.get("segment"))
        contrib_ok = isinstance(attr.get("contribution_pct"), (int, float)) \
            and attr["contribution_pct"] >= rob.get("min_contribution_pct", 0)
        learned = measure_ok and seg_ok and contrib_ok
        notes.append(f"mesure trouvée par les données : {'✓' if measure_ok else '✗'} "
                     f"({inv.get('metric_label', '—')})")
        notes.append(f"cause trouvée par la valeur : {'✓' if seg_ok else '✗'} "
                     f"({attr.get('segment', '—')} · {attr.get('contribution_pct', '—')}%)")
        if rob.get("expected_role"):
            role_ok, role_detail = _role_ok((r.decisions or {}).get("decisions", []),
                                             rob["expected_role"])
            learned = learned and role_ok
            notes.append(f"décideur par le concept : {'✓' if role_ok else '✗'} ({role_detail})")

    verdict = "APPRIS ✅" if learned else ("À CORRIGER ❌" if learned is False else "—")
    print(f"\n▹ {name:<26} {verdict}")
    print(f"    difficulté : {exp.get('difficulty', '—')}")
    print(f"    idéal      : {exp.get('ideal', '—')}")
    for nt in notes:
        print(f"    · {nt}")
    concl = (inv.get("conclusion") or r.message or "").replace("Conclusion : ", "")
    print(f"    Noreon dit : {concl[:150]}")
    if exp.get("known_limitation"):
        print(f"    ⚠ limite   : {exp['known_limitation']}")


def run(scenarios: list[str], threshold: int) -> int:
    print("\n" + "═" * 78)
    print(" BENCHMARK — Gold Standard ⇄ Noreon")
    print("═" * 78)
    total, counted, failures = 0, 0, 0
    for sc in scenarios:
        exp = json.loads((HERE / sc / "expected.json").read_text(encoding="utf-8"))
        if not db_available(sc):
            print(f"\n▹ {sc:<14} SKIP — base noreon_demo_{sc} injoignable "
                  f"(lancer demo/setup_scenario.sh {sc}).")
            continue
        r, _ = analyze(sc, exp["question"])
        rows = _score(_extract(r), exp)
        got_pts = sum(w for _, _, w, ok, _ in rows if ok)
        counted += 1
        total += got_pts
        status = "✅ PASS" if got_pts >= threshold else "❌ FAIL"
        if got_pts < threshold:
            failures += 1
        print(f"\n▹ {sc:<14} {got_pts:3d}/100  {status}")
        for _, lbl, w, ok, detail in rows:
            mark = "✓" if ok else "✗"
            print(f"    {mark} {lbl:<28} {w:>2} pts   {detail}")
        _print_reasoning(r)

    if counted:
        avg = total / counted
        print("\n" + "─" * 78)
        print(f" MOYENNE : {avg:.0f}/100 sur {counted} scénario(s) · "
              f"{counted - failures} PASS / {failures} FAIL · seuil {threshold}")
        print("─" * 78)
    else:
        print("\nAucune base de démo joignable. Lancez demo/setup_scenario.sh <scenario>.")
        return 0
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    threshold = PASS_THRESHOLD
    args, only_challenge = [], False
    i = 0
    while i < len(argv):
        if argv[i] == "--threshold":
            threshold = int(argv[i + 1])
            i += 2
        elif argv[i] == "--challenge":
            only_challenge = True
            i += 1
        else:
            args.append(argv[i])
            i += 1

    challenges = discover_challenges()
    if only_challenge:
        _print_challenge_header()
        for sc in challenges:
            run_challenge(sc)
        print("\nLes challenges ne sont pas notés : le but n'est pas d'avoir 100, "
              "c'est que le moteur apprenne.")
        return 0

    scenarios = args or list(SCENARIO_QUESTIONS)
    unknown = [s for s in scenarios if s not in SCENARIO_QUESTIONS]
    if unknown:
        print(f"Scénario(s) inconnu(s) : {', '.join(unknown)}")
        return 2
    code = run(scenarios, threshold)

    # Section challenge (non bloquante) : cas conçus pour casser le moteur.
    if not args and challenges:
        _print_challenge_header()
        for sc in challenges:
            run_challenge(sc)
        print("\nLes challenges ne sont pas notés (le but est d'APPRENDRE, pas d'avoir 100).")
    return code


def _print_challenge_header() -> None:
    print("\n" + "═" * 78)
    print(" NOREON CHALLENGE — scénarios conçus pour casser le moteur")
    print("═" * 78)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
