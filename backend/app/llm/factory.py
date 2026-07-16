"""Sélection du fournisseur LLM selon la configuration du tenant (§6).

Le code métier appelle `get_provider_for_tenant(...)` et reçoit un objet
conforme à l'interface `LLMProvider`, sans jamais savoir lequel est utilisé.
"""
from __future__ import annotations

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.heuristic import HeuristicProvider
from app.llm.providers import build_cloud_provider


def get_provider(provider: str | None = None, model: str | None = None) -> LLMProvider:
    provider = (provider or settings.llm_provider or "heuristic").lower()
    model = model if model is not None else settings.llm_model

    if provider in ("heuristic", "offline", ""):
        return HeuristicProvider()

    cloud = build_cloud_provider(provider, model or "")
    if cloud is not None:
        return cloud

    # Repli sûr : jamais d'échec dur si la clé manque.
    return HeuristicProvider()


def get_provider_for_tenant(tenant_settings) -> LLMProvider:
    """`tenant_settings` : instance TenantSettings (ou None)."""
    if tenant_settings is None:
        return get_provider()
    return get_provider(
        provider=getattr(tenant_settings, "llm_provider", None),
        model=getattr(tenant_settings, "llm_model", None),
    )
