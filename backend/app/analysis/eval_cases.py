"""Phase 2 — C3b : CORPUS d'évaluation du planificateur (≥ 50 cas uniques).

Chaque cas décrit une DEMANDE et les attentes au niveau INTERPRÉTATION (objectifs,
types, arêtes de dépendance, termes non résolus) + l'éligibilité au modèle simple
(gpt-oss-20b) et un `split` development/holdout pour éviter le sur-ajustement du
prompt. DOMAINE-AGNOSTIQUE : les attentes portent sur la STRUCTURE, jamais sur des
noms de tables/colonnes ; plusieurs domaines (retail, CRM, générique) évitent le
sur-apprentissage retail.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    min_goals: int
    expect_types: frozenset
    depends_on_edges: tuple[tuple[str, str], ...] = ()
    expect_unresolved_roles: frozenset = field(default_factory=frozenset)
    expect_clarification: bool = False
    simple_eligible: bool = False           # → gpt-oss-20b, sinon gpt-oss-120b
    split: str = "development"              # development | holdout
    domain: str = "generic"                # retail | crm | generic
    note: str = ""


def _s(id, q, t, *, dom="generic", split="development", note=""):
    """Cas SIMPLE (20b éligible) — un objectif count/aggregate/ranking."""
    return EvalCase(id=id, question=q, min_goals=1, expect_types=frozenset({t}),
                    simple_eligible=True, split=split, domain=dom, note=note)


def _c(id, q, types, *, dom="generic", split="development", edges=(), unresolved=frozenset(),
       clar=False, min_goals=1, note=""):
    """Cas COMPLEXE (120b)."""
    return EvalCase(id=id, question=q, min_goals=min_goals, expect_types=frozenset(types),
                    depends_on_edges=edges, expect_unresolved_roles=unresolved,
                    expect_clarification=clar, simple_eligible=False, split=split,
                    domain=dom, note=note)


CASES: list[EvalCase] = [
    # ============================ SIMPLES (20b) ============================
    _s("s_count_customers", "Combien de clients ai-je ?", "count", dom="retail"),
    _s("s_count_orders", "Nombre de commandes au total", "count", dom="retail"),
    _s("s_count_products", "Combien de produits au catalogue", "count", dom="retail"),
    _s("s_count_stores", "Combien de magasins", "count", dom="retail"),
    _s("s_count_users", "Nombre d'utilisateurs enregistrés", "count", dom="crm"),
    _s("s_count_subs", "Combien d'abonnements actifs", "count", dom="crm"),
    _s("s_count_tickets", "Nombre de tickets au total", "count", dom="crm"),
    _s("s_count_invoices", "Combien de factures émises", "count", dom="generic"),
    _s("s_agg_revenue", "Chiffre d'affaires total", "aggregate", dom="retail"),
    _s("s_agg_basket", "Panier moyen", "aggregate", dom="retail"),
    _s("s_agg_billed", "Montant total facturé", "aggregate", dom="generic"),
    _s("s_agg_refunds", "Somme des remboursements", "aggregate", dom="retail", split="holdout"),
    _s("s_agg_avg_res", "Durée moyenne de résolution des tickets", "aggregate", dom="crm"),
    _s("s_agg_mrr", "Revenu récurrent total", "aggregate", dom="crm", split="holdout"),
    _s("s_rank_products", "Classement des produits par montant vendu", "ranking", dom="retail"),
    _s("s_rank_customers", "Top 10 des clients par chiffre d'affaires", "ranking", dom="retail"),
    _s("s_rank_cities", "Classement des villes par nombre de clients", "ranking", dom="generic"),
    _s("s_rank_agents", "Top agents par tickets résolus", "ranking", dom="crm", split="holdout"),
    _s("s_rank_categories", "Classement des catégories par montant", "ranking", dom="retail"),
    _s("s_count_by_city", "Combien de clients par ville", "count", dom="generic",
       note="count + 1 dimension même table"),
    _s("s_count_by_cat", "Nombre de produits par catégorie", "count", dom="retail"),
    _s("s_agg_avg_amount", "Montant moyen des commandes", "aggregate", dom="retail", split="holdout"),

    # ============================ COMPLEXES (120b) ============================
    # -- RFM / segmentation --
    _c("rfm_full",
       "Fais une analyse des clients qui achètent nos produits : un score de "
       "segmentation RFM, quels produits par segment, et par quelle tranche d'âge",
       ("segmentation", "affinity", "distribution"), dom="retail", min_goals=3,
       edges=(("affinity", "segmentation"),), unresolved=frozenset({"dimension"}),
       note="cas de référence RFM"),
    _c("rfm_no_acronym",
       "Segmente mes clients selon leur valeur et regarde quels types de produits chaque segment achète",
       ("segmentation", "affinity"), dom="retail", min_goals=2,
       edges=(("affinity", "segmentation"),)),
    _c("seg_frequency", "Segmente mes clients par fréquence d'achat", ("segmentation",), dom="retail"),
    _c("seg_value_crm", "Segmente les comptes par valeur contractuelle", ("segmentation",), dom="crm",
       split="holdout"),
    # -- Affinité --
    _c("affinity_basket", "Quels produits sont achetés ensemble", ("affinity",), dom="retail"),
    _c("affinity_by_seg", "Analyse l'affinité produits par segment de clientèle",
       ("segmentation", "affinity"), dom="retail", min_goals=2, edges=(("affinity", "segmentation"),),
       split="holdout"),
    # -- Cohortes --
    _c("cohort_signup", "Analyse de cohortes des inscriptions par mois", ("cohort",), dom="crm"),
    _c("cohort_retention", "Rétention par cohorte mensuelle", ("cohort",), dom="crm", split="holdout"),
    # -- Corrélation --
    _c("corr_age_basket", "Quelle corrélation entre l'âge et le panier moyen", ("correlation",),
       dom="retail"),
    _c("corr_tenure_value", "Corrélation entre l'ancienneté du compte et sa valeur", ("correlation",),
       dom="crm"),
    # -- Croisement 2 dimensions --
    _c("cross_prod_region", "Répartis le chiffre d'affaires par produit et par région",
       ("attribution",), dom="retail"),
    _c("cross_month_store", "Ventes par mois et par magasin", ("attribution",), dom="retail",
       split="holdout"),
    _c("cross_agent_cat", "Tickets par agent et par catégorie", ("attribution",), dom="crm"),
    # -- Binning / intervalles dérivés --
    _c("bin_age", "Répartis mes clients par tranche d'âge", ("distribution",), dom="generic",
       unresolved=frozenset({"dimension"}), note="âge peut être absent"),
    _c("bin_basket", "Répartis le CA par tranche de panier", ("distribution",), dom="retail",
       split="holdout"),
    # -- Multi-objectifs --
    _c("four_objectives",
       "Fais une segmentation RFM, une analyse de cohortes des inscriptions, la corrélation "
       "entre ancienneté et valeur, et un classement des produits",
       ("segmentation", "cohort", "correlation", "ranking"), dom="retail", min_goals=4),
    _c("seg_then_retention",
       "Segmente mes clients puis analyse la rétention par segment",
       ("segmentation", "cohort"), dom="crm", min_goals=2, edges=(("cohort", "segmentation"),),
       split="holdout"),
    # -- Ambiguïté --
    _c("ambig_ttc", "Analyse le chiffre d'affaires par segment (HT ou TTC ?)", ("attribution",),
       dom="retail", clar=True),
    _c("ambig_margin", "Analyse la marge par produit (brute ou nette ?)", ("attribution",),
       dom="retail", clar=True, split="holdout"),
    # -- Tendance / causal --
    _c("trend_revenue", "Montre l'évolution du chiffre d'affaires par mois", ("trend",), dom="retail"),
    _c("trend_signups", "Tendance des inscriptions sur l'année", ("trend",), dom="crm"),
    _c("trend_mrr", "Évolution du revenu récurrent", ("trend",), dom="crm", split="holdout"),
    _c("causal_sales", "Pourquoi le chiffre d'affaires baisse-t-il depuis trois mois ?",
       ("attribution",), dom="retail"),
    _c("causal_churn", "Pourquoi le taux d'attrition augmente-t-il ?", ("attribution",), dom="crm"),
    _c("causal_basket", "Qu'est-ce qui explique la hausse du panier moyen web", ("attribution",),
       dom="retail", split="holdout"),
    # -- Distribution --
    _c("dist_basket", "Distribution des montants de commande", ("distribution",), dom="retail"),
    _c("dist_tenure", "Répartition des comptes par ancienneté", ("distribution",), dom="crm",
       split="holdout"),
    # -- Prévision --
    _c("forecast_sales", "Prévision des ventes pour le trimestre prochain", ("trend",), dom="retail"),
    _c("forecast_churn", "Prédire quels clients vont résilier", ("segmentation",), dom="crm",
       split="holdout", note="prédiction → complexe"),
    # -- Entonnoir --
    _c("funnel_conversion", "Analyse l'entonnoir de conversion des prospects", ("distribution",),
       dom="crm"),
    # -- Ranking avec méthode --
    _c("rank_affinity", "Top produits par affinité d'achat", ("affinity", "ranking"), dom="retail",
       min_goals=1, split="holdout"),
]

CASES_BY_ID = {c.id: c for c in CASES}

DEVELOPMENT = [c for c in CASES if c.split == "development"]
HOLDOUT = [c for c in CASES if c.split == "holdout"]
SIMPLE_CASES = [c for c in CASES if c.simple_eligible]
COMPLEX_CASES = [c for c in CASES if not c.simple_eligible]
