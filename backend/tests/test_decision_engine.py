from __future__ import annotations

from app.services import chronicle
from app.services import decision_engine as de
from app.services import decision_memory as dm


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


def test_restate_intent():
    """L'objectif est reformulé, pas juste catégorisé."""
    assert de.restate_intent("Pourquoi les ventes baissent ?", metric_label="total de amount_ttc",
                             trend_direction="baisse") == "Diagnostiquer une baisse de amount_ttc"
    assert "Comparer les performances par magasin" == de.restate_intent(
        "Compare les magasins", top_dimension="magasin (stores)")


def test_decision_impact_justification_and_inaction():
    """L2 impact estimé + L3 justification + L4 projection prudente de l'inaction."""
    d = de.decide(
        question="Pourquoi le CA baisse ?", metric_label="le CA",
        trend_direction="baisse", trend_pct=-12.0, recent_rate=-3.2,
        drivers=[{"dimension": "magasin", "segment": "Store 3", "share": 65}],
    )
    assert d is not None
    assert d.restated == "Diagnostiquer une baisse de le CA".replace("de le", "de le")  # tolère l'article
    reseau = next(x for x in d.decisions if x["role"] == "Directeur réseau")
    # L2 : fourchette d'impact + confiance.
    assert reseau["impact"] and "%" in reseau["impact"]
    assert reseau["impact_confidence"] in ("Faible", "Moyenne", "Élevée")
    # L3 : justification (« parce que … »).
    assert reseau["justification"].startswith("parce que") and "65" in reseau["justification"]
    # L4 : projection prudente, formulée sans certitude.
    assert d.inaction and "projection" in d.inaction.lower()
    assert "pas d'une prédiction" in d.inaction

    # Pas de projection d'inaction si la tendance n'est pas baissière.
    d2 = de.decide(question="Pourquoi le CA monte ?", metric_label="le CA",
                   trend_direction="hausse", trend_pct=8.0, recent_rate=2.0,
                   drivers=[{"dimension": "magasin", "segment": "Store 1", "share": 50}])
    assert d2.inaction is None


def test_decision_effort_impact_matrix():
    """M2 : chaque décision porte effort, impact_level et un rang d'étoiles,
    et la liste est triée par priorité (étoiles) décroissante."""
    d = de.decide(
        question="Pourquoi le CA baisse ?", metric_label="le CA",
        trend_direction="baisse", trend_pct=-15.0,
        drivers=[
            {"dimension": "magasin", "segment": "Store 3", "share": 70},
            {"dimension": "loyalty (customers)", "segment": "fidèles", "share": 25},
        ],
    )
    assert d is not None
    for x in d.decisions:
        assert x["effort"] in ("Faible", "Moyen", "Élevé")
        assert x["impact_level"] in ("Faible", "Moyen", "Élevé")
        assert 1 <= x["stars"] <= 5
    # Tri par priorité décroissante (rapport effort/impact).
    stars = [x["stars"] for x in d.decisions]
    assert stars == sorted(stars, reverse=True)
    # CRM (effort Faible) doit être bien classé grâce au faible effort.
    crm = next(x for x in d.decisions if x["role"] == "Responsable CRM")
    assert crm["effort"] == "Faible"


def test_decision_history_annotation():
    """M3 : une reco proche d'une décision déjà qualifiée est annotée."""
    called = {}

    def history(role, reco):
        called[role] = reco
        return "Déjà appliquée avec succès dans un contexte similaire." \
            if role == "Directeur réseau" else None

    d = de.decide(
        question="Pourquoi le CA baisse ?", metric_label="le CA",
        trend_direction="baisse", trend_pct=-12.0,
        drivers=[{"dimension": "magasin", "segment": "Store 3", "share": 65}],
        history=history,
    )
    assert d is not None
    reseau = next(x for x in d.decisions if x["role"] == "Directeur réseau")
    assert reseau["history"] == "Déjà appliquée avec succès dans un contexte similaire."
    fin = next(x for x in d.decisions if x["role"] == "Directeur financier")
    assert fin["history"] is None


def test_decision_memory_annotate():
    """La mémoire rapproche deux formulations proches et privilégie le succès."""
    class Rec:
        def __init__(self, role, reco, status):
            self.role, self.recommendation, self.status = role, reco, status

    records = [
        Rec("Directeur réseau",
            "Auditer localement « Lyon » : conditions du point de vente, "
            "concurrence, exécution terrain.", "successful"),
        Rec("Directeur réseau",
            "Auditer localement « Lyon » : conditions du point de vente, "
            "concurrence, exécution terrain.", "retained"),
    ]
    # Une reco proche (autre segment) sur le même rôle → annotée « succès ».
    txt = dm.annotate(
        records, "Directeur réseau",
        "Auditer localement « Paris » : conditions du point de vente, "
        "concurrence, exécution terrain.")
    assert txt == "Déjà appliquée avec succès dans un contexte similaire."
    # Rôle différent → pas d'annotation.
    assert dm.annotate(records, "Responsable CRM", "Lancer une campagne ciblée.") is None
    # Recouvrement lexical insuffisant → pas d'annotation.
    assert dm.annotate(records, "Directeur réseau", "Revoir les prix produits.") is None
