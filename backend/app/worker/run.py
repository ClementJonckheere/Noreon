"""Point d'entrée du worker RQ : `python -m app.worker.run`.

Consomme les files de priorité (scan d'abord, puis profilage à faible
priorité). Nécessite Redis. En dev sans Redis, les tâches s'exécutent en
in-process via app.worker.queue.enqueue.
"""
from __future__ import annotations

import redis
from rq import Queue, Worker

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.worker.queue import QUEUE_PROFILING, QUEUE_SCAN

log = get_logger("noreon.worker")


def main() -> None:
    configure_logging()
    conn = redis.Redis.from_url(settings.redis_url)
    queues = [Queue(QUEUE_SCAN, connection=conn), Queue(QUEUE_PROFILING, connection=conn)]
    log.info("Worker Noreon démarré (files : %s)", [q.name for q in queues])
    Worker(queues, connection=conn).work(with_scheduler=True)


if __name__ == "__main__":
    main()
