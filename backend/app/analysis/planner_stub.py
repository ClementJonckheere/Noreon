"""Planificateur DÉTERMINISTE — TEST / DÉVELOPPEMENT UNIQUEMENT.

⚠️ Jamais câblé en production : ni la factory (`app/llm/factory.py`) ni
`build_planner_provider` ne l'importent. Il sert à exercer le pipeline
Interpreter → contrats sans clé ni réseau, et à alimenter le benchmark C3.
Aucun repli de production ne doit produire un plan simulé.
"""
from __future__ import annotations

import json

from app.llm.base import AnalysisResult, LLMProvider, SQLGenerationResult

# Plan RFM valide (3 objectifs, DAG, terme âge non résolu relié à g3).
_RFM = {
    "plan_schema_version": "1.2",
    "goals": [
        {"id": "g1", "priority": 1, "type": "segmentation",
         "intent_text": "Segmenter les clients par valeur (RFM)",
         "entity_ref": "concept:customer",
         "metrics": [{"ref": "metric:recency", "of_ref": "concept:order"},
                     {"ref": "metric:frequency", "of_ref": "concept:order"},
                     {"ref": "metric:net_revenue", "of_ref": "concept:order"}],
         "method": {"name": "rfm", "params": {}}, "depends_on": []},
        {"id": "g2", "priority": 2, "type": "affinity",
         "intent_text": "Affinité produits par segment",
         "entity_ref": "concept:product", "depends_on": ["g1"]},
        {"id": "g3", "priority": 3, "type": "distribution",
         "intent_text": "Répartition par tranche d'âge",
         "entity_ref": None, "binning_requested": True, "depends_on": []},
    ],
    "unresolved_terms": [
        {"goal_id": "g3", "term": "tranche d'âge", "role": "dimension",
         "source_span": "par quelle tranche d'âge", "reason": "aucune dimension âge dans le catalogue"}
    ],
}

# Repli déterministe pour les questions simples (une agrégation).
_SINGLE = {
    "plan_schema_version": "1.2",
    "goals": [
        {"id": "g1", "priority": 1, "type": "aggregate",
         "intent_text": "Agrégation d'une mesure",
         "entity_ref": "concept:order",
         "metrics": [{"ref": "metric:net_revenue", "of_ref": "concept:order"}],
         "depends_on": []}
    ],
    "unresolved_terms": [],
}


class StubPlanner(LLMProvider):
    """Fournisseur factice : renvoie un plan déterministe selon des marqueurs
    présents dans le prompt utilisateur. TEST/DEV uniquement."""

    name = "stub"

    def generate_sql(self, *a, **k) -> SQLGenerationResult:  # pragma: no cover
        raise NotImplementedError("stub : planification uniquement")

    def analyze_results(self, *a, **k) -> AnalysisResult:  # pragma: no cover
        raise NotImplementedError("stub : planification uniquement")

    def plan(self, *, system: str, user: str, json_schema: dict) -> str:
        u = user.lower()
        if "rfm" in u or "segment" in u:
            return json.dumps(_RFM)
        return json.dumps(_SINGLE)
