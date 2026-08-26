"""Configuration centrale de Noreon.

Toutes les valeurs sont lues depuis l'environnement (préfixe NOREON_) et
peuvent être surchargées par tenant dans la table `tenant_settings`.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_dotenv_into_environ() -> None:
    """Charge `.env` dans `os.environ` (sans écraser une variable shell existante).

    Pydantic lit déjà `.env` pour les champs `NOREON_*`, mais les SECRETS
    non préfixés (ex. `OVH_AI_ENDPOINTS_ACCESS_TOKEN`, lus via `os.getenv`)
    ne seraient pas vus sans ça. Cherche `.env` dans le CWD puis à la racine
    de `backend/`. Sans dépendance externe."""
    here = Path(__file__).resolve()
    for candidate in (Path.cwd() / ".env", here.parents[2] / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


_load_dotenv_into_environ()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOREON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"

    # Base interne
    database_url: str = "postgresql+psycopg://noreon:noreon@localhost:5432/noreon"
    redis_url: str = "redis://localhost:6379/0"

    # Chiffrement des credentials sources (clé maîtresse — coffre en prod)
    secret_key: str = "dev-insecure-key-change-me"

    # Couche LLM
    llm_provider: str = "heuristic"
    llm_model: str = ""

    # Planificateur analytique (Phase 2) — OVHcloud AI Endpoints (OpenAI-compat).
    # Le SECRET (OVH_AI_ENDPOINTS_ACCESS_TOKEN) est lu via os.environ, jamais ici.
    # Aucun modèle par défaut : une config incomplète produit une erreur explicite.
    ovh_base_url: str = ""
    ovh_model: str = ""
    # Routage à deux modèles (C3) : principal (toute complexité) et simple
    # (demandes strictement count/aggregate/ranking, sans méthode/dépendance).
    ovh_model_main: str = ""
    ovh_model_simple: str = ""

    # Shadow Planner (Phase 2, C5) — le planner LLM est OBSERVÉ, jamais décisionnaire.
    # Seuls `legacy` et `shadow` sont EXÉCUTABLES en C5 ; `active`/`canary` sont
    # réservés (contrat futur) et REFUSÉS explicitement (unsupported_mode) tant que
    # l'activation n'est pas câblée — jamais un shadow déguisé.
    planner_mode: str = "legacy"                 # legacy | shadow | (active/canary → refusés)
    planner_shadow_sample_rate: float = 1.0      # [0,1] — 100 % en dev/démo, abaissable en réel
    planner_shadow_timeout_ms: int = 8_000       # budget dur par évaluation shadow
    planner_shadow_max_concurrency: int = 4      # cap in-flight (protège les ressources)
    planner_shadow_executor: str = "inprocess"   # inprocess | rq
    planner_shadow_store_plan: bool = True       # conserver llm_plan_json (rétention COURTE)
    planner_shadow_plan_retention_days: int = 14 # purge du plan complet (projections gardées +longtemps)
    planner_shadow_store_sanitized_question: bool = False  # opt-in — jamais le prompt brut

    # Garde-fous SQL (défauts globaux, configurables par tenant)
    sql_timeout_seconds: int = 60
    sql_row_limit: int = 10_000
    sql_max_cost: float = 1_000_000.0
    sql_max_concurrent_per_connection: int = 1

    # Profilage
    profiling_sample_threshold: int = 1_000_000
    profiling_sample_size: int = 100_000

    cors_origins: str = "http://localhost:3000"

    # Auth (Module 11) : en dev, on autorise le repli sur l'en-tête X-Tenant
    # (comme un admin implicite) pour les tests et l'exploration API. À mettre
    # à False en production pour EXIGER un jeton d'authentification.
    dev_auth_fallback: bool = True

    # Répertoire de stockage des fichiers sources (CSV/Excel) et de leur
    # matérialisation SQLite (V1.0).
    data_dir: str = "./data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
