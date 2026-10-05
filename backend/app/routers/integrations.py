import secrets
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..config import settings
from ..db import get_db
from ..models import ApiKey, Cpse, IngestJob, User, Webhook
from ..security import STEWARD, current_user, new_api_key, require
from ..services.sap_service import export_mapping, test_connection
from ..services.webhook_service import EVENTS, send
from ..workers.queue import queue
from .ingest import job_out

router = APIRouter(prefix="/integrations", tags=["integrations"])
ADMIN = ("admin",)
MEDIA = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv"}


def _url(v: str) -> str:
    v = v.strip()
    if not v.lower().startswith(("http://", "https://")):
        raise ValueError("must start with http:// or https://")
    return v


def _events(v: list[str]) -> list[str]:
    if bad := [e for e in v if e not in EVENTS and e != "*"]:
        raise ValueError(f"unknown events {bad}; allowed: {EVENTS + ['*']}")
    return sorted(set(v))


# ---- SAP-format mapping export (per CPSE) ------------------------------------------------------------------------

@router.get("/export/{cpse_code}")
def export(cpse_code: str, format: Literal["xlsx", "csv"] = "xlsx", db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    code = cpse_code.strip().upper()
    cpse = db.query(Cpse).filter_by(code=code).first()
    if not cpse:
        raise HTTPException(404, "Unknown CPSE")
    if user.role == "cpse_user" and user.cpse_id != cpse.id:
        raise HTTPException(403, "You can export only your own CPSE's mapping")
    data = export_mapping(db, code, format)
    write_audit(db, user, "export", "cpse", code, None, {"format": format, "bytes": len(data)})
    db.commit()
    return Response(data, media_type=MEDIA[format],
                    headers={"Content-Disposition": f'attachment; filename="NMC_mapping_{code}.{format}"'})


# ---- SAP OData (API_PRODUCT_SRV) ---------------------------------------------------------------------------------

class SapIn(BaseModel):
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=200)

    @field_validator("base_url")
    @classmethod
    def check_url(cls, v):
        return _url(v) if v else v


class SapPullIn(SapIn):
    cpse_code: str
    top: int = Field(200, ge=1, le=5000)


@router.get("/sap")
def sap_status(_=Depends(require(*STEWARD))):
    return {"configured": bool(settings.sap_base_url and settings.sap_api_key), "base_url": settings.sap_base_url}


@router.post("/sap/test")
def sap_test(body: SapIn, _=Depends(require(*STEWARD))):
    base, key = body.base_url or settings.sap_base_url, body.api_key or settings.sap_api_key
    if not base or not key:
        raise HTTPException(422, "Set SAP_BASE_URL and SAP_API_KEY in .env, or send base_url and api_key")
    return test_connection(base.rstrip("/"), key)


@router.post("/sap/pull")
def sap_pull(body: SapPullIn, db: Session = Depends(get_db), user: User = Depends(require(*STEWARD))):
    """Queues sap_pull_job; progress streams on /ingest/{id}/events like a file upload."""
    if not (body.base_url or settings.sap_base_url) or not (body.api_key or settings.sap_api_key):
        raise HTTPException(422, "SAP connection is not configured")
    cpse = db.query(Cpse).filter_by(code=body.cpse_code.strip().upper()).first()
    if not cpse:
        raise HTTPException(404, "Unknown CPSE")
    job = IngestJob(cpse_id=cpse.id, filename="SAP OData · API_PRODUCT_SRV", source="sap", status="queued",
                    stage="queued", created_by=user.id,
                    column_map={"MATNR": "MATNR", "MAKTX": "MAKTX", "MEINS": "MEINS", "MATKL": "MATKL"})
    db.add(job)
    db.flush()                                         # assigns job.id for the audit row
    write_audit(db, user, "sap_pull", "ingest_job", job.id, None, {"cpse": cpse.code, "top": body.top})
    db.commit()
    try:
        queue.enqueue("app.workers.jobs.sap_pull_job", str(job.id), body.top,
                      body.base_url.rstrip("/") if body.base_url else None, body.api_key, job_timeout=7200)
    except Exception:
        job.status, job.stage, job.report = "error", "error", {"error": "The job queue (Redis) is unavailable."}
        db.commit()
        raise HTTPException(503, "Job queue unavailable") from None
    return job_out(job)


# ---- API keys (machine clients get read-only access) -------------------------------------------------------------

class KeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


def key_out(k: ApiKey) -> dict:
    return {"id": str(k.id), "name": k.name, "prefix": k.prefix,
            "created_at": k.created_at.isoformat() if k.created_at else None}


@router.get("/api-keys")
def list_keys(db: Session = Depends(get_db), _=Depends(require(*ADMIN))):
    return [key_out(k) for k in db.query(ApiKey).order_by(ApiKey.created_at.desc())]


@router.post("/api-keys")
def create_key(body: KeyIn, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    raw, prefix, key_hash = new_api_key()
    k = ApiKey(name=body.name.strip(), prefix=prefix, key_hash=key_hash)
    db.add(k)
    db.flush()
    write_audit(db, user, "create", "api_key", k.id, None, {"name": k.name, "prefix": prefix})
    db.commit()
    return {**key_out(k), "key": raw, "note": "Copy this key now. It is stored only as a hash and cannot be shown again."}


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    k = db.get(ApiKey, key_id)
    if not k:
        raise HTTPException(404, "API key not found")
    write_audit(db, user, "revoke", "api_key", k.id, {"name": k.name, "prefix": k.prefix}, None)
    db.delete(k)
    db.commit()
    return {"ok": True}


# ---- Webhooks (HMAC-SHA256 signed) -------------------------------------------------------------------------------

class HookIn(BaseModel):
    url: str = Field(max_length=500)
    events: list[str] = Field(min_length=1)
    secret: str | None = Field(None, min_length=16, max_length=80)

    @field_validator("url")
    @classmethod
    def check_url(cls, v):
        return _url(v)

    @field_validator("events")
    @classmethod
    def check_events(cls, v):
        return _events(v)


class HookPatch(BaseModel):
    active: bool | None = None
    events: list[str] | None = Field(None, min_length=1)

    @field_validator("events")
    @classmethod
    def check_events(cls, v):
        return _events(v) if v is not None else v


def hook_out(h: Webhook) -> dict:
    return {"id": str(h.id), "url": h.url, "events": h.events, "active": h.active, "last_status": h.last_status,
            "secret_hint": h.secret[:4] + "…"}


def _hook(db: Session, hook_id: uuid.UUID) -> Webhook:
    h = db.get(Webhook, hook_id)
    if not h:
        raise HTTPException(404, "Webhook not found")
    return h


@router.get("/webhooks")
def list_hooks(db: Session = Depends(get_db), _=Depends(require(*ADMIN))):
    return {"items": [hook_out(h) for h in db.query(Webhook).order_by(Webhook.url)], "events": EVENTS}


@router.post("/webhooks")
def create_hook(body: HookIn, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    h = Webhook(url=body.url, events=body.events, secret=body.secret or secrets.token_hex(24), active=True)
    db.add(h)
    db.flush()
    write_audit(db, user, "create", "webhook", h.id, None, {"url": h.url, "events": h.events})
    db.commit()
    return {**hook_out(h), "secret": h.secret, "note": "Use this secret to verify X-EkCode-Signature."}


@router.patch("/webhooks/{hook_id}")
def update_hook(hook_id: uuid.UUID, body: HookPatch, db: Session = Depends(get_db),
                user: User = Depends(require(*ADMIN))):
    h = _hook(db, hook_id)
    before = {"active": h.active, "events": list(h.events or [])}
    if body.active is not None:
        h.active = body.active
    if body.events is not None:
        h.events = body.events
    write_audit(db, user, "update", "webhook", h.id, before, {"active": h.active, "events": list(h.events or [])})
    db.commit()
    return hook_out(h)


@router.delete("/webhooks/{hook_id}")
def delete_hook(hook_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    h = _hook(db, hook_id)
    write_audit(db, user, "delete", "webhook", h.id, {"url": h.url, "events": h.events}, None)
    db.delete(h)
    db.commit()
    return {"ok": True}


@router.post("/webhooks/{hook_id}/test")
def test_hook(hook_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    """Sends a signed `webhook.test` event right now and reports the receiver's HTTP status (0 = unreachable)."""
    h = _hook(db, hook_id)
    status = send(h, "webhook.test", {"message": "EkCode webhook test", "by": user.email})
    db.commit()
    return {"ok": 200 <= status < 300, "status": status}
