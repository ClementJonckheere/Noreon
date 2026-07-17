"""Application FastAPI de Noreon (V0.1)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.api.routes import (
    alerts,
    chat,
    connections,
    definitions,
    health,
    profiling,
    quality,
    schema,
    semantic,
    settings as settings_routes,
)

configure_logging()

app = FastAPI(
    title="Noreon API",
    version="0.1.0",
    description=(
        "Data Analyst IA autonome — V0.1 : connexion PostgreSQL, scan "
        "automatique, profilage échantillonné, chat SQL avec garde-fous "
        "d'exécution et transparence."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(connections.router)
app.include_router(schema.router)
app.include_router(profiling.router)
app.include_router(quality.router)
app.include_router(semantic.router)
app.include_router(semantic.concepts_router)
app.include_router(definitions.router)
app.include_router(settings_routes.router)
app.include_router(alerts.router)
app.include_router(chat.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "Noreon",
        "tagline": "Comprendre. Relier. Éclairer.",
        "version": "0.1.0",
        "docs": "/docs",
    }
