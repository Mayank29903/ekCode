import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import contains, get_db
from ..models import AuditLog
from ..security import require
from ..services.sap_service import safe_cell

router = APIRouter(tags=["audit"])
AUDIT_READERS = ("admin", "data_steward", "auditor")
EXPORT_LIMIT = 50_000


def audit_out(a: AuditLog) -> dict:
    return {"id": a.id, "at": a.at.isoformat() if a.at else None, "actor": str(a.actor) if a.actor else None,
            "actor_email": a.actor_email, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
            "before": a.before, "after": a.after, "reason": a.reason}


def audit_filters(entity: str | None = None, action: str | None = None, actor: str | None = None,
                  entity_id: str | None = None, q: str | None = None,
                  since: datetime | None = None, until: datetime | None = None) -> dict:
    return {"entity": entity, "action": action, "actor": actor, "entity_id": entity_id, "q": q,
            "since": since, "until": until}


def filtered(db: Session, entity=None, action=None, actor=None, entity_id=None, q=None, since=None, until=None):
    query = db.query(AuditLog)
    if entity:
        query = query.filter(AuditLog.entity == entity)
    if action:
        query = query.filter(AuditLog.action == action)
    if actor:
        query = query.filter(AuditLog.actor_email.ilike(contains(actor), escape="\\"))
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if q:
        pat = contains(q)
        query = query.filter(or_(AuditLog.entity_id.ilike(pat, escape="\\"), AuditLog.reason.ilike(pat, escape="\\"),
                                 AuditLog.actor_email.ilike(pat, escape="\\")))
    if since:
        query = query.filter(AuditLog.at >= since)
    if until:
        query = query.filter(AuditLog.at <= until)
    return query


@router.get("/audit")
def audit_trail(f: dict = Depends(audit_filters), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), _=Depends(require(*AUDIT_READERS))):
    """FR11: the append-only trail, newest first, with the facets the filter bar needs."""
    query = filtered(db, **f)
    total = query.count()
    items = query.order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    actions = [a for (a,) in db.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    entities = [e for (e,) in db.query(AuditLog.entity).distinct().order_by(AuditLog.entity)]
    return {"items": [audit_out(a) for a in items], "total": total, "actions": actions, "entities": entities}


@router.get("/audit/export")
def audit_export(f: dict = Depends(audit_filters), db: Session = Depends(get_db),
                 _=Depends(require(*AUDIT_READERS))):
    """The same filters as the list, as a CSV file (newest first, capped at 50,000 rows)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["at", "actor_email", "action", "entity", "entity_id", "reason", "before", "after"])
    for a in filtered(db, **f).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(EXPORT_LIMIT):
        w.writerow([safe_cell(v) for v in (
            a.at.isoformat() if a.at else "", a.actor_email or "", a.action, a.entity, a.entity_id, a.reason or "",
            json.dumps(a.before) if a.before is not None else "", json.dumps(a.after) if a.after is not None else "")])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="ekcode_audit_{stamp}.csv"'})
