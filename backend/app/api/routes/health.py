from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "noreon",
        "version": "0.1.0",
        "env": settings.env,
        "llm_provider": settings.llm_provider,
    }
