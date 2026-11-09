"""Fournisseurs LLM cloud/on-premise (appels REST via httpx, sans SDK propriétaire).

Chaque fournisseur implémente l'interface `LLMProvider`. Les clés sont lues
depuis l'environnement et ne transitent jamais par les logs. Ces classes ne
sont instanciées que si une clé est configurée pour le tenant ; sinon la
factory retombe sur le `HeuristicProvider` hors-ligne.
"""
from __future__ import annotations

import json
import os

import httpx

from app.core.logging import get_logger
from app.llm.base import (
    AnalysisResult,
    LLMMessage,
    LLMProvider,
    SQLGenerationResult,
)
from app.llm.prompts import (
    ANALYSIS_SYSTEM_PROMPT,
    SQL_SYSTEM_PROMPT,
    build_schema_user_prompt,
)

log = get_logger("noreon.llm")

_TIMEOUT = httpx.Timeout(60.0)


def _extract_json(text: str) -> dict:
    """Extrait le premier objet JSON d'une réponse LLM (robuste au bavardage)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{") :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Réponse LLM sans JSON exploitable")
    return json.loads(text[start : end + 1])


def _to_sql_result(data: dict) -> SQLGenerationResult:
    return SQLGenerationResult(
        sql=(data.get("sql") or "").strip(),
        tables_used=list(data.get("tables_used") or []),
        columns_used=list(data.get("columns_used") or []),
        assumptions=list(data.get("assumptions") or []),
        clarification_needed=data.get("clarification_needed") or None,
        rationale=data.get("rationale") or "",
    )


def _to_analysis(data: dict) -> AnalysisResult:
    return AnalysisResult(
        summary=data.get("summary") or "",
        observations=list(data.get("observations") or []),
        anomalies=list(data.get("anomalies") or []),
        recommendations=list(data.get("recommendations") or []),
    )


class _HTTPChatProvider(LLMProvider):
    """Base commune pour les API de type « chat completions »."""

    name = "http"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - I/O réseau
        raise NotImplementedError

    def generate_sql(
        self,
        question: str,
        schema_context: str,
        dialect: str = "postgres",
        history: list[LLMMessage] | None = None,
    ) -> SQLGenerationResult:
        system = SQL_SYSTEM_PROMPT.format(dialect=dialect)
        user = build_schema_user_prompt(question, schema_context)
        raw = self._chat(system, user)
        return _to_sql_result(_extract_json(raw))

    def analyze_results(
        self, question: str, sql: str, columns: list[str], rows: list[list]
    ) -> AnalysisResult:
        preview = {"columns": columns, "rows": rows[:50]}
        user = f"Question: {question}\nSQL: {sql}\nRésultats anonymisés: {json.dumps(preview, default=str)}"
        raw = self._chat(ANALYSIS_SYSTEM_PROMPT, user)
        return _to_analysis(_extract_json(raw))


class OpenAIProvider(_HTTPChatProvider):
    name = "openai"

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model or "gpt-5.1",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class MistralProvider(_HTTPChatProvider):
    name = "mistral"

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover
        resp = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model or "mistral-large-latest",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(_HTTPChatProvider):
    name = "anthropic"

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model or "claude-sonnet-5",
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "mistral": MistralProvider,
}


def build_cloud_provider(provider: str, model: str) -> LLMProvider | None:
    """Instancie un fournisseur cloud si sa clé est disponible, sinon None."""
    cls = _CLASSES.get(provider)
    if cls is None:
        return None
    key = os.getenv(_KEY_ENV[provider], "")
    if not key:
        log.warning("Fournisseur '%s' demandé mais clé absente — repli heuristique.", provider)
        return None
    return cls(model=model, api_key=key)


# --- Planificateur analytique (Phase 2) : OVHcloud AI Endpoints -------------
class PlannerConfigError(RuntimeError):
    """Configuration du planificateur absente/incomplète — erreur EXPLICITE
    (jamais un changement silencieux de fournisseur ni un modèle par défaut)."""


class OVHcloudProvider(_HTTPChatProvider):
    """OVHcloud AI Endpoints — OpenAI-compatible (`/v1/chat/completions`).
    Le `base_url` inclut déjà `/v1`. Aucun modèle par défaut."""

    name = "ovhcloud"

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        super().__init__(model=model, api_key=api_key)
        self._base_url = base_url.rstrip("/")

    def _post(self, system: str, user: str, response_format: dict) -> str:  # pragma: no cover - I/O réseau
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": response_format,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - I/O réseau
        return self._post(system, user, {"type": "json_object"})

    def plan(self, *, system: str, user: str, json_schema: dict) -> str:  # pragma: no cover - I/O réseau
        # Sortie CONTRAINTE au JSON Schema (généré par les modèles Pydantic).
        rf = {"type": "json_schema",
              "json_schema": {"name": "analysis_interpretation", "strict": True, "schema": json_schema}}
        return self._post(system, user, rf)


_OVH_TOKEN_ENV = "OVH_AI_ENDPOINTS_ACCESS_TOKEN"


def build_planner_provider() -> LLMProvider:
    """Fournisseur du PLANIFICATEUR analytique, strictement selon la config.

    - `NOREON_LLM_PROVIDER=ovhcloud` explicite (aucun mode anonyme) ;
    - `NOREON_OVH_BASE_URL`, `NOREON_OVH_MODEL` et `OVH_AI_ENDPOINTS_ACCESS_TOKEN`
      requis (aucun modèle par défaut) ;
    - toute absence lève `PlannerConfigError` — le repli honnête (offline) est
      décidé PAR L'APPELANT, jamais par un changement silencieux ici.
    """
    from app.core.config import settings

    provider = (settings.llm_provider or "").lower()
    if provider != "ovhcloud":
        raise PlannerConfigError(
            f"NOREON_LLM_PROVIDER='{provider or '(vide)'}' n'est pas un planificateur."
        )
    base_url = settings.ovh_base_url
    model = settings.ovh_model
    token = os.getenv(_OVH_TOKEN_ENV, "")
    missing = [name for name, val in (
        ("NOREON_OVH_BASE_URL", base_url), ("NOREON_OVH_MODEL", model),
        (_OVH_TOKEN_ENV, token)) if not val]
    if missing:
        raise PlannerConfigError("Configuration OVHcloud incomplète : " + ", ".join(missing))
    return OVHcloudProvider(model=model, api_key=token, base_url=base_url)
