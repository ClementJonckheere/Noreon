from __future__ import annotations

from app.services import chronicle
from app.services import decision_engine as de


def test_chronicle_rhythm_narration():
    """La chronologie raconte le RYTHME : stabilité initiale → déclin → accélération."""
    ch = chronicle.build(
        ["periode", "valeur"],
        [["2025-02", 100], ["2025-03", 100], ["2025-04", 98],
         ["2025-05", 93], ["2025-06", 88], ["2025-07", 76]],
        metric_label="le CA",
    )
    assert ch is not None
    assert ch.direction == "baisse" and ch.streak == 4
    assert ch.stable_prefix == "2025-03"
    assert ch.tempo == "accélération"
    n = ch.narrative.lower()
    assert "stabilité" in n and "accélération" in n and "progressivement" in n


def test_detect_intent():
    assert de.detect_intent("Pourquoi les ventes baissent ?") == "diagnostic"
    assert de.detect_intent("Compare les magasins") == "comparaison"
    assert de.detect_intent("Prépare le rapport mensuel pour le comité") == "reporting"
    assert de.detect_intent("Montre les commandes") == "exploration"


def test_decision_engine_roles():
    """Mêmes données, décisions différentes selon le rôle (finance + réseau + CRM)."""
    d = de.decide(
        question="Pourquoi les ventes baissent ?", metric_label="le CA",
        trend_direction="baisse", trend_pct=-12.0,
        drivers=[
            {"dimension": "magasin", "segment": "Store 3", "share": 65},
            {"dimension": "loyalty_points (customers)", "segment": "fidèles", "share": 30},
        ],
    )
    assert d is not None
    roles = [x["role"] for x in d.decisions]
    assert "Directeur financier" in roles       # présent car mesure en baisse
    assert "Directeur réseau" in roles           # driver = magasin
    assert "Responsable CRM" in roles            # driver = fidélité
    # La priorité réseau cite le segment et sa part.
    reseau = next(x for x in d.decisions if x["role"] == "Directeur réseau")
    assert "Store 3" in reseau["priority"] and "65" in reseau["priority"]


def test_decision_engine_none_when_no_signal():
    """Pas de tendance monétaire ni de driver exploitable → pas de décisions."""
    assert de.decide(question="Liste les clients", metric_label="l'effectif",
                     trend_direction=None, trend_pct=None, drivers=[]) is None
