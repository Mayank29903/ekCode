from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, defer

from ..db import get_db
from ..models import CodeMapping, Cpse, MatchPair, RawMaterial, User
from ..security import STEWARD, current_user, require
from ..services.cluster_service import approve_pair, promote_singletons, reject_pair
from ..workers.queue import enqueue_safely

router = APIRouter(prefix="/review", tags=["review"])
Status = Literal["suggested", "approved", "rejected", "blocked"]
Decision = Literal["approve", "reject"]


def pairs_out(db: Session, pairs: list[MatchPair]) -> list[dict]:
    """Loads both sides of every pair in three queries instead of three per side."""
    rids = {p.a_id for p in pairs} | {p.b_id for p in pairs}
    if not rids:
        return []
    raws = {r.id: r for r in db.query(RawMaterial).options(defer(RawMaterial.embedding))
            .filter(RawMaterial.id.in_(rids))}
    nmcs = dict(db.query(CodeMapping.raw_material_id, CodeMapping.nmc).filter(CodeMapping.raw_material_id.in_(rids)))
    cpses = dict(db.query(Cpse.id, Cpse.code))

    def side(rid: int) -> dict:
        r = raws[rid]
        return {"id": r.id, "cpse": cpses.get(r.cpse_id), "legacy_code": r.legacy_code,
                "description": r.description, "uom": r.uom_raw, "attributes": r.attributes or {},
                "source": r.source, "nmc": nmcs.get(rid),
                "spend": float(r.unit_price or 0) * float(r.annual_qty or 0)}

    return [{"id": p.id, "score": p.score, "match_type": p.match_type, "status": p.status, "impact": p.impact,
             "explanation": p.explanation, "gate_failures": p.gate_failures, "features": p.features,
             "a": side(p.a_id), "b": side(p.b_id)} for p in pairs]


def pair_out(db: Session, p: MatchPair) -> dict:
    return pairs_out(db, [p])[0]


@router.get("/queue")
def review_queue(status: Status = "suggested", type: str | None = None,
                 limit: int = Query(40, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), _=Depends(current_user)):
    q = db.query(MatchPair).filter(MatchPair.status == status)
    if type:
        q = q.filter(MatchPair.match_type == type)
    if status in ("approved", "rejected"):
        q = q.order_by(MatchPair.decided_at.desc().nulls_last(), MatchPair.id.desc())
    else:
        q = q.order_by(MatchPair.impact.desc(), MatchPair.id)     # FR5: highest impact first
    items = q.offset(offset).limit(limit).all()
    counts = dict(db.query(MatchPair.status, func.count()).group_by(MatchPair.status).all())
    by_type = dict(db.query(MatchPair.match_type, func.count()).filter(MatchPair.status == "suggested")
                   .group_by(MatchPair.match_type).all())
    return {"items": pairs_out(db, items), "counts": counts, "by_type": by_type}


class DecisionIn(BaseModel):
    decision: Decision
    reason: str | None = Field(None, max_length=500)


def _locked(db: Session, pair_id: int) -> MatchPair | None:
    return db.query(MatchPair).filter_by(id=pair_id).with_for_update().first()


@router.post("/{pair_id}/decision")
def decide(pair_id: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require(*STEWARD))):
    p = _locked(db, pair_id)
    if body.decision == "approve":
        nmc = approve_pair(db, p, user, body.reason)
        db.commit()
        enqueue_safely("app.services.webhook_service.deliver", "mapping.approved", {"pair": p.id, "nmc": nmc})
        return {"ok": True, "nmc": nmc}
    reject_pair(db, p, user, body.reason)
    db.commit()
    return {"ok": True}


class BulkIn(BaseModel):
    ids: list[int] = Field(max_length=500)
    decision: Decision


@router.post("/bulk")
def bulk(body: BulkIn, db: Session = Depends(get_db), user: User = Depends(require(*STEWARD))):
    """Each pair is its own transaction: one conflict does not undo the rest (FLOW §4)."""
    done, failed = 0, []
    for pid in body.ids:
        try:
            p = _locked(db, pid)
            if body.decision == "approve":
                nmc = approve_pair(db, p, user, "bulk")
                db.commit()
                enqueue_safely("app.services.webhook_service.deliver", "mapping.approved", {"pair": pid, "nmc": nmc})
            else:
                reject_pair(db, p, user, "bulk")
                db.commit()
            done += 1
        except HTTPException as e:
            db.rollback()
            failed.append({"id": pid, "error": e.detail})
        except SQLAlchemyError:
            db.rollback()
            failed.append({"id": pid, "error": "changed by someone else at the same moment; try again"})
    return {"done": done, "failed": failed}


@router.post("/promote-singletons")
def singletons(db: Session = Depends(get_db), user: User = Depends(require(*STEWARD))):
    created = promote_singletons(db, user)
    if created:
        enqueue_safely("app.services.webhook_service.deliver", "singletons.issued", {"created": created})
    return {"created": created}
