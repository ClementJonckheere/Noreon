"""Protection ANTI-RETAIL du Decision Engine.

Le moteur de décision ne doit dépendre d'AUCUN vocabulaire retail. Ces tests le
font tourner sur un scénario SaaS (« Pourquoi le MRR recule ? »), et sur le cas
brutal d'un entrepreneur solo sans acteur ni responsabilité (contexte vide). Dans
les deux cas Noreon doit produire des recommandations utiles et mesurables, sans
jamais nommer un magasin, une région, un produit ou un Directeur réseau.
"""
from __future__ import annotations

from app.services import decision_engine as de
from app.services import measurement as meas
from app.services.business_context import EMPTY

_RETAIL = ("magasin", "paca", "produit", "gamme", "directeur réseau", "point de vente",
           "réseau", "assortiment", "supply chain", "crm")

# Facteurs SaaS d'un recul de MRR — aucune notion retail.
_MRR_DRIVERS = [
    {"dimension": "plan (subscriptions)", "segment": "Starter", "share": 58},
    {"dimension": "customer_type (customers)", "segment": "renouvellements", "share": 27},
]


def _assert_no_retail(ds):
    blob = " ".join(
        f"{x['role']} {x['priority']} {x['recommendation']} {x['justification']}".lower()
        for x in ds.decisions
    )
    for term in _RETAIL:
        assert term not in blob, f"terme retail « {term} » fuité dans une recommandation"


def test_mrr_saas_generic_recommendations_no_retail():
    """MRR en recul, contexte vide → recommandations génériques, zéro retail."""
    ds = de.decide(
        question="Pourquoi le MRR recule ?", metric_label="le MRR",
        trend_direction="baisse", trend_pct=-9.0, recent_rate=-3.0,
        drivers=_MRR_DRIVERS, context=EMPTY,
    )
    assert ds is not None and ds.decisions
    # Aucune décision ne présume d'un rôle d'organisation (chip de rôle vide).
    assert all(x["role"] == "" for x in ds.decisions)
    # Le facteur dominant est cité et une action est proposée.
    top = ds.decisions[0]
    assert "Starter" in top["priority"] or "Starter" in top["recommendation"]
    assert "action possible" in top["recommendation"].lower()
    assert "le MRR" in top["recommendation"]  # « mesuré sur le MRR »
    _assert_no_retail(ds)

    # Finding → recommandation → MeasurementPlan éventuel : la classification du
    # protocole de mesure est elle aussi générique (jamais « inconclusif » forcé).
    mtype = meas.classify_action(top["recommendation"])
    assert mtype in ("impact", "performance", "completion", "diagnostic")


def test_solo_entrepreneur_no_actors_no_responsibilities():
    """Cas brutal : actors = [] et responsibilities = []. Le moteur fonctionne."""
    assert not EMPTY.actors and not EMPTY.responsibilities
    ds = de.decide(
        question="Pourquoi mon chiffre baisse ?", metric_label="le revenu",
        trend_direction="baisse", trend_pct=-11.0,
        drivers=[{"dimension": "canal_acquisition", "segment": "referral", "share": 44}],
        context=EMPTY,
    )
    assert ds is not None and ds.decisions
    assert all(x["role"] == "" for x in ds.decisions)
    _assert_no_retail(ds)


def test_decision_engine_source_has_no_retail_literals():
    """Tout le vocabulaire retail a quitté le moteur (il vit dans les fixtures)."""
    import inspect

    from app.services import responsibility
    for module in (de, responsibility):
        src = inspect.getsource(module).lower()
        for term in ("magasin", "paca", "directeur réseau", "gamme de produits",
                     "supply chain", "point de vente", "île-de-france"):
            assert term not in src, f"« {term} » ne doit plus vivre dans {module.__name__}"
