"""Couche d'abstraction LLM (cahier des charges §6).

« Interface unique multi-fournisseurs ; aucun appel direct à un SDK
propriétaire dans le code métier ; configuration par tenant. »

Le code métier ne connaît QUE cette interface. Les implémentations concrètes
(OpenAI, Anthropic, Mistral, on-premise, heuristique offline) sont
interchangeables et sélectionnées par la factory selon la config du tenant.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class SQLGenerationResult:
    """Résultat structuré d'une génération SQL par le LLM."""

    sql: str
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    clarification_needed: str | None = None
    rationale: str = ""


@dataclass
class AnalysisResult:
    summary: str
    observations: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class LLMProvider(abc.ABC):
    """Contrat commun à tous les fournisseurs de modèles."""

    name: str = "abstract"

    @abc.abstractmethod
    def generate_sql(
        self,
        question: str,
        schema_context: str,
        dialect: str = "postgres",
        history: list[LLMMessage] | None = None,
    ) -> SQLGenerationResult:
        """Traduit une question en langage naturel en SQL (lecture seule)."""

    @abc.abstractmethod
    def analyze_results(
        self,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list],
    ) -> AnalysisResult:
        """Produit une interprétation à partir de résultats ANONYMISÉS.

        Contrat Privacy Engine : `rows` ne doit contenir aucune donnée brute
        identifiante — uniquement des agrégats/pseudonymisations.
        """
