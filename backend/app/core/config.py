"""Configuration centrale de Noreon.

Toutes les valeurs sont lues depuis l'environnement (préfixe NOREON_) et
peuvent être surchargées par tenant dans la table `tenant_settings`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Garde-fous SQL (défauts globaux, configurables par tenant)
    sql_timeout_seconds: int = 60
    sql_row_limit: int = 10_000
    sql_max_cost: float = 1_000_000.0
    sql_max_concurrent_per_connection: int = 1

    # Profilage
    profiling_sample_threshold: int = 1_000_000
    profiling_sample_size: int = 100_000

    cors_origins: str = "http://localhost:3000"

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
