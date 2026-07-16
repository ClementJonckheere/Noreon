"""File d'attente des tâches asynchrones (RQ / Redis) avec repli in-process.

Cahier des charges §6 : « Worker de jobs (scan, profilage, rapports planifiés)
avec files de priorité ». On utilise RQ + Redis. Si Redis est indisponible
(ex. environnement de dev sans Redis), on exécute la tâche dans un thread pour
que le produit reste fonctionnel.
"""
from __future__ import annotations

import threading

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("noreon.queue")

# Files de priorité : profilage = faible priorité (tâche de fond).
QUEUE_PROFILING = "profiling"
QUEUE_SCAN = "scan"


def _redis_available() -> bool:
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:  # noqa: BLE001
        return False


def enqueue(func, *args, queue: str = QUEUE_PROFILING, **kwargs) -> str:
    """Enfile une tâche. Renvoie un identifiant (job RQ ou 'inline:...')."""
    if _redis_available():
        try:
            import redis  # noqa: PLC0415
            from rq import Queue  # noqa: PLC0415

            conn = redis.Redis.from_url(settings.redis_url)
            q = Queue(queue, connection=conn)
            job = q.enqueue(func, *args, **kwargs, job_timeout=3600)
            log.info("Tâche %s enfilée sur RQ (%s)", job.id, queue)
            return job.id
        except Exception as exc:  # noqa: BLE001
            log.warning("Échec enqueue RQ, repli in-process : %s", exc)

    # Repli : exécution dans un thread daemon (dev sans Redis).
    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    t.start()
    return f"inline:{t.name}"
