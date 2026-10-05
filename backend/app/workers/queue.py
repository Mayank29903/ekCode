import logging

from redis import Redis
from rq import Queue

from ..config import settings

log = logging.getLogger(__name__)
queue = Queue("ekcode", connection=Redis.from_url(settings.redis_url), default_timeout=3600)


def enqueue_safely(func: str, *args) -> bool:
    """Best-effort enqueue for side effects (webhooks) that must not fail the request that caused them."""
    try:
        queue.enqueue(func, *args)
        return True
    except Exception as e:  # Redis down: the decision is already committed; log and move on
        log.warning("could not enqueue %s: %s", func, e)
        return False
