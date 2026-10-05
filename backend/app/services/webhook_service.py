"""HMAC-signed webhooks (FR12). Each event fans out to one RQ job per hook, so one slow or failing receiver
never delays another, and a failed delivery is retried with back-off (10 s, 1 min, 5 min).

Body: {"id": delivery id, "event", "sent_at", "data"}. Receivers verify
    hmac.compare_digest(sign(secret, raw_body), request.headers["X-EkCode-Signature"])
and can reject replays by remembering "id" and checking "sent_at"."""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx

from ..db import SessionLocal
from ..models import Webhook

log = logging.getLogger(__name__)
EVENTS = ["mapping.approved", "material.updated", "singletons.issued"]
RETRY_INTERVALS = [10, 60, 300]


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def wants(h: Webhook, event: str) -> bool:
    events = h.events or []
    return event in events or "*" in events


def send(h: Webhook, event: str, payload: dict) -> int:
    """POST one signed event to one hook; returns the HTTP status (0 = unreachable) and records it on the hook."""
    delivery = str(uuid.uuid4())
    body = json.dumps({"id": delivery, "event": event, "sent_at": datetime.now(timezone.utc).isoformat(),
                       "data": payload}, default=str).encode()
    try:
        r = httpx.post(h.url, content=body, timeout=10, follow_redirects=False,
                       headers={"Content-Type": "application/json", "User-Agent": "EkCode-Webhook/1.0",
                                "X-EkCode-Event": event, "X-EkCode-Delivery": delivery,
                                "X-EkCode-Signature": sign(h.secret, body)})
        h.last_status = r.status_code
    except httpx.HTTPError as e:
        log.info("webhook %s unreachable: %s", h.url, e)
        h.last_status = 0
    return h.last_status


def deliver(event: str, payload: dict) -> int:
    """RQ job, enqueued after the change has committed (FLOW §4): fan out to every interested active hook."""
    from rq import Retry

    from ..workers.queue import queue
    with SessionLocal() as db:
        hook_ids = [str(h.id) for h in db.query(Webhook).filter(Webhook.active.is_(True)) if wants(h, event)]
    for hook_id in hook_ids:
        queue.enqueue("app.services.webhook_service.deliver_one", hook_id, event, payload,
                      retry=Retry(max=len(RETRY_INTERVALS), interval=RETRY_INTERVALS), job_timeout=60)
    return len(hook_ids)


def deliver_one(hook_id: str, event: str, payload: dict) -> int:
    """RQ job for one hook. Raising on a non-2xx answer makes RQ retry it later."""
    with SessionLocal() as db:
        h = db.get(Webhook, uuid.UUID(hook_id))
        if h is None or not h.active:
            return 0
        url, status = h.url, send(h, event, payload)
        db.commit()
    if not 200 <= status < 300:
        raise RuntimeError(f"webhook {url} answered {status or 'nothing'}")
    return status
