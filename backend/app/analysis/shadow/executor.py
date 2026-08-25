"""Phase 2 — C5 : exécuteurs shadow (non bloquants).

Contrat : `ShadowExecutor.submit(envelope)` déclenche l'évaluation shadow SANS
jamais bloquer/retarder la requête chat. Le worker ne reçoit JAMAIS la session
SQLAlchemy de la requête HTTP : il reçoit un `envelope` (IDs + données déjà
sanitizées) et ouvre SA PROPRE session (via `run_shadow_from_envelope`).

- `InProcessShadowExecutor` : pool de threads borné (dev/test).
- `RQShadowExecutor` : file Redis/RQ (staging/prod). Même l'enqueue est isolé
  (un Redis lent ne doit jamais ajouter de secondes au chat) → il part sur un
  thread détaché, best-effort.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

from app.core.logging import get_logger

log = get_logger("noreon.planner.shadow.executor")


class ShadowExecutor(ABC):
    @abstractmethod
    def submit(self, envelope: dict) -> str:
        """Déclenche l'évaluation. Renvoie un statut de dispatch
        ('submitted' | 'dropped' | ...). Ne lève JAMAIS vers l'appelant."""


class InProcessShadowExecutor(ShadowExecutor):
    """Pool borné en process. Dépose le job et rend la main immédiatement.
    Si le pool est saturé (cap in-flight), on DROPPE (log) plutôt que bloquer."""

    def __init__(self, *, max_concurrency: int = 4, runner=None):
        self._pool = ThreadPoolExecutor(max_workers=max(1, max_concurrency),
                                        thread_name_prefix="shadow")
        self._cap = max(1, max_concurrency)
        self._inflight = 0
        self._lock = threading.Lock()
        # Injectable pour les tests ; par défaut le worker réel (session propre).
        self._runner = runner or _default_runner

    def submit(self, envelope: dict) -> str:
        with self._lock:
            if self._inflight >= self._cap:
                log.warning("shadow dropped (in-flight cap %d atteint)", self._cap)
                return "dropped"
            self._inflight += 1
        try:
            self._pool.submit(self._run, envelope)
            return "submitted"
        except Exception as exc:  # noqa: BLE001 - le dispatch ne doit jamais casser le chat
            with self._lock:
                self._inflight -= 1
            log.warning("shadow submit a échoué : %s", exc)
            return "dropped"

    def _run(self, envelope: dict) -> None:
        try:
            self._runner(envelope)                 # ouvre SA PROPRE session
        except Exception as exc:  # noqa: BLE001 - isolation totale
            log.warning("shadow run a échoué (isolé) : %s", exc)
        finally:
            with self._lock:
                self._inflight -= 1


class RQShadowExecutor(ShadowExecutor):
    """Enqueue vers Redis/RQ. L'enqueue lui-même est détaché (thread) pour qu'un
    Redis lent n'ajoute jamais de latence au chat."""

    def __init__(self, *, queue=None, job_path: str = "app.analysis.shadow.service.run_shadow_from_envelope"):
        self._queue = queue
        self._job_path = job_path
        self._dispatch = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shadow-enqueue")

    def submit(self, envelope: dict) -> str:
        try:
            self._dispatch.submit(self._enqueue, envelope)
            return "submitted"
        except Exception as exc:  # noqa: BLE001
            log.warning("shadow enqueue-dispatch a échoué : %s", exc)
            return "dropped"

    def _enqueue(self, envelope: dict) -> None:
        try:
            queue = self._queue or _default_rq_queue()
            if queue is None:
                log.warning("shadow RQ indisponible — évaluation ignorée")
                return
            queue.enqueue(self._job_path, envelope)
        except Exception as exc:  # noqa: BLE001 - Redis lent/indispo : jamais fatal
            log.warning("shadow enqueue Redis a échoué (isolé) : %s", exc)


def _default_runner(envelope: dict) -> None:
    from app.analysis.shadow.service import run_shadow_from_envelope
    run_shadow_from_envelope(envelope)


def _default_rq_queue():  # pragma: no cover - dépend de l'infra Redis
    try:
        from redis import Redis
        from rq import Queue

        from app.core.config import settings
        return Queue("shadow", connection=Redis.from_url(settings.redis_url))
    except Exception:  # noqa: BLE001
        return None


def build_executor(settings) -> ShadowExecutor:
    if (settings.planner_shadow_executor or "inprocess").lower() == "rq":
        return RQShadowExecutor()
    return InProcessShadowExecutor(max_concurrency=settings.planner_shadow_max_concurrency)
