from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.orm import Session, defer

from ekml import taxonomy
from ekml.extract import canonical_value
from ekml.gates import HARD_KEYS
from ekml.nmc import is_valid
from ekml.standardize import standard_description

from ..audit import write_audit
from ..db import contains, get_db
from ..models import AuditLog, CodeMapping, Cpse, MatchPair, NationalMaterial, RawMaterial, User
from ..security import STEWARD, current_user, require
from ..services.cluster_service import legacy_ref, resolve_active
from ..workers.queue import enqueue_safely
from .audit_log import audit_out
from .review import pairs_out

router = APIRouter(tags=["materials"])
EDITABLE_KEYS = set(HARD_KEYS) | {"standard", "coating"}


# ---- shared helpers (also used by search and graph) -------------------------------------------------------------

def member_stats():
    """Per-NMC aggregates over its mapped legacy items."""
    spend = func.coalesce(func.sum(RawMaterial.unit_price * RawMaterial.annual_qty), 0)
    return (select(CodeMapping.nmc.label("nmc"),
                   func.count(RawMaterial.id).label("legacy_count"),
                   func.count(distinct(RawMaterial.cpse_id)).label("cpse_count"),
                   spend.label("spend"),
                   func.bool_and(RawMaterial.source == "synthetic").label("synthetic"),
                   func.array_agg(distinct(Cpse.code)).label("cpses"))
            .join(RawMaterial, RawMaterial.id == CodeMapping.raw_material_id)
            .join(Cpse, Cpse.id == RawMaterial.cpse_id)
            .group_by(CodeMapping.nmc)
            .subquery())


def material_out(nm: NationalMaterial, legacy_count=0, cpse_count=0, spend=0, synthetic=False, cpses=None) -> dict:
    return {"nmc": nm.nmc, "noun": nm.noun, "standard_description": nm.standard_description,
            "attributes": nm.attributes or {}, "status": nm.status, "successor_nmc": nm.successor_nmc,
            "unspsc": nm.unspsc, "uom_code": nm.uom_code, "version": nm.version,
            "legacy_count": int(legacy_count or 0), "cpse_count": int(cpse_count or 0), "spend": float(spend or 0),
            "synthetic": bool(synthetic), "cpses": sorted(cpses or []),
            "created_at": nm.created_at.isoformat() if nm.created_at else None,
            "updated_at": nm.updated_at.isoformat() if nm.updated_at else None}


def legacy_out(r: RawMaterial, cpse_code: str | None, nmc: str | None = None) -> dict:
    return {"id": r.id, "cpse": cpse_code, "legacy_code": r.legacy_code, "description": r.description,
            "long_text": r.long_text, "uom": r.uom_raw, "uom_code": r.uom_code, "material_group": r.material_group,
            "unit_price": float(r.unit_price) if r.unit_price is not None else None,
            "annual_qty": float(r.annual_qty) if r.annual_qty is not None else None,
            "spend": float(r.unit_price or 0) * float(r.annual_qty or 0),
            "attributes": r.attributes or {}, "attr_confidence": r.attr_confidence or {},
            "source": r.source, "status": r.status, "nmc": nmc}


def _material(db: Session, nmc: str, lock: bool = False) -> NationalMaterial:
    q = db.query(NationalMaterial).filter(NationalMaterial.nmc == nmc.strip().upper())
    nm = (q.with_for_update() if lock else q).first()
    if not nm:
        raise HTTPException(404, "National material not found")
    return nm


# ---- national materials -----------------------------------------------------------------------------------------

@router.get("/materials")
def list_materials(q: str | None = None, status: Literal["active", "deprecated", "all"] = "active",
                   noun: str | None = None, cpse: str | None = None,
                   sort: Literal["recent", "spend", "legacy", "nmc"] = "recent",
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db), _=Depends(current_user)):
    s = member_stats()
    query = (db.query(NationalMaterial, s.c.legacy_count, s.c.cpse_count, s.c.spend, s.c.synthetic, s.c.cpses)
             .outerjoin(s, s.c.nmc == NationalMaterial.nmc))
    if status != "all":
        query = query.filter(NationalMaterial.status == status)
    if noun:
        query = query.filter(NationalMaterial.noun == noun.strip().upper())
    if cpse:
        in_cpse = (select(CodeMapping.nmc).join(RawMaterial, RawMaterial.id == CodeMapping.raw_material_id)
                   .join(Cpse, Cpse.id == RawMaterial.cpse_id).where(Cpse.code == cpse.strip().upper()))
        query = query.filter(NationalMaterial.nmc.in_(in_cpse))
    if q:
        pat = contains(q)
        by_legacy = (select(CodeMapping.nmc).join(RawMaterial, RawMaterial.id == CodeMapping.raw_material_id)
                     .where(RawMaterial.legacy_code.ilike(pat, escape="\\")))
        query = query.filter(or_(NationalMaterial.nmc.ilike(pat, escape="\\"),
                                 NationalMaterial.standard_description.ilike(pat, escape="\\"),
                                 NationalMaterial.nmc.in_(by_legacy)))
    total = query.count()
    order = {"recent": NationalMaterial.created_at.desc(), "spend": s.c.spend.desc().nulls_last(),
             "legacy": s.c.legacy_count.desc().nulls_last(), "nmc": NationalMaterial.nmc.asc()}[sort]
    rows = query.order_by(order, NationalMaterial.nmc).offset(offset).limit(limit).all()
    nouns = [n for (n,) in db.query(NationalMaterial.noun).filter(NationalMaterial.noun.is_not(None))
             .distinct().order_by(NationalMaterial.noun)]
    return {"items": [material_out(*row) for row in rows], "total": total, "nouns": nouns}


@router.get("/materials/{nmc}")
def material_detail(nmc: str, db: Session = Depends(get_db), _=Depends(current_user)):
    nm = _material(db, nmc)
    active = resolve_active(db, nm.nmc)
    members = (db.query(RawMaterial, Cpse.code, CodeMapping)
               .options(defer(RawMaterial.embedding))
               .join(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
               .join(Cpse, Cpse.id == RawMaterial.cpse_id)
               .filter(CodeMapping.nmc == nm.nmc).order_by(Cpse.code, RawMaterial.legacy_code).all())
    legacy = [{**legacy_out(r, code, nm.nmc), "confidence": m.confidence,
               "effective_from": m.effective_from.isoformat() if m.effective_from else None} for r, code, m in members]
    ids = [r.id for r, _, _ in members]
    pairs = (db.query(MatchPair).filter(or_(MatchPair.a_id.in_(ids), MatchPair.b_id.in_(ids)))
             .order_by(MatchPair.created_at.desc()).limit(30).all()) if ids else []
    refs = [legacy_ref(r) for r, _, _ in members]
    history = (db.query(AuditLog).filter(or_(
        and_(AuditLog.entity == "national_material", AuditLog.entity_id == nm.nmc),
        and_(AuditLog.entity == "legacy_code", AuditLog.entity_id.in_(refs or [""]))))
        .order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(60).all())
    predecessors = [p for (p,) in db.query(NationalMaterial.nmc).filter(NationalMaterial.successor_nmc == nm.nmc)]
    vec = (db.query(RawMaterial.embedding).join(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
           .filter(CodeMapping.nmc == nm.nmc, RawMaterial.embedding.is_not(None)).limit(1).scalar())
    suggestions = taxonomy.suggest(nm.standard_description, 3, np.asarray(vec, dtype=np.float32)) \
        if vec is not None else []
    spend = sum(item["spend"] for item in legacy)
    return {**material_out(nm, len(legacy), len({x["cpse"] for x in legacy}), spend,
                           bool(legacy) and all(x["source"] == "synthetic" for x in legacy),
                           list({x["cpse"] for x in legacy})),
            "active_nmc": active.nmc if active else None, "valid_check_digit": is_valid(nm.nmc),
            "legacy": legacy, "predecessors": predecessors, "pairs": pairs_out(db, pairs),
            "history": [audit_out(a) for a in history], "unspsc_suggestions": suggestions}


class MaterialPatch(BaseModel):
    standard_description: str | None = Field(None, min_length=3, max_length=500)
    attributes: dict[str, str] | None = None
    unspsc: str | None = Field(None, pattern=r"^\d{8}$")
    regenerate_description: bool = False
    reason: str | None = Field(None, max_length=500)


def _snapshot(nm: NationalMaterial) -> dict:
    return {"standard_description": nm.standard_description, "attributes": dict(nm.attributes or {}),
            "noun": nm.noun, "unspsc": nm.unspsc}


def _clean_attributes(raw: dict[str, str]) -> dict:
    out = {}
    for key, value in raw.items():
        k = key.strip().lower()
        if k != "noun" and k not in EDITABLE_KEYS:
            raise HTTPException(422, f"Unknown attribute: {key}")
        if not str(value).strip():
            continue                                    # an empty value removes the attribute
        clean = canonical_value(k, value)
        if clean is None:
            raise HTTPException(422, f"Cannot read {key} = {value!r}")
        out[k] = clean
    return out


@router.patch("/materials/{nmc}")
def update_material(nmc: str, body: MaterialPatch, db: Session = Depends(get_db),
                    user: User = Depends(require(*STEWARD))):
    """Steward edits (FR6/G3). Values are canonicalized like extracted ones, so gates keep working."""
    nm = _material(db, nmc, lock=True)
    if nm.status != "active":
        raise HTTPException(409, f"{nm.nmc} is deprecated; edit {nm.successor_nmc} instead")
    before = _snapshot(nm)
    if body.attributes is not None:
        nm.attributes = _clean_attributes(body.attributes)
        nm.noun = nm.attributes.get("noun")
    if body.regenerate_description:
        nm.standard_description = standard_description(nm.attributes or {}, nm.standard_description)
    elif body.standard_description:
        nm.standard_description = body.standard_description.strip()
    if body.unspsc:
        nm.unspsc = body.unspsc
    after = _snapshot(nm)
    if after == before:
        return {"changed": False, **material_out(nm)}
    nm.version += 1
    write_audit(db, user, "update", "national_material", nm.nmc, before, after, body.reason)
    db.commit()
    enqueue_safely("app.services.webhook_service.deliver", "material.updated", {"nmc": nm.nmc, "version": nm.version})
    return {"changed": True, **material_out(nm)}


# ---- legacy (CPSE) materials ------------------------------------------------------------------------------------

@router.get("/legacy")
def list_legacy(q: str | None = None, cpse: str | None = None,
                state: Literal["all", "mapped", "unmapped"] = "all", source: str | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), _=Depends(current_user)):
    query = (db.query(RawMaterial, Cpse.code, CodeMapping.nmc).options(defer(RawMaterial.embedding))
             .join(Cpse, Cpse.id == RawMaterial.cpse_id)
             .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id))
    if cpse:
        query = query.filter(Cpse.code == cpse.strip().upper())
    if state == "mapped":
        query = query.filter(CodeMapping.id.is_not(None))
    elif state == "unmapped":
        query = query.filter(CodeMapping.id.is_(None))
    if source:
        query = query.filter(RawMaterial.source == source)
    if q:
        pat = contains(q)
        query = query.filter(or_(RawMaterial.legacy_code.ilike(pat, escape="\\"),
                                 RawMaterial.description.ilike(pat, escape="\\")))
    total = query.count()
    rows = query.order_by(RawMaterial.id.desc()).offset(offset).limit(limit).all()
    return {"items": [legacy_out(r, code, nmc) for r, code, nmc in rows], "total": total}


@router.get("/legacy-items/{rid}")
def legacy_detail(rid: int, db: Session = Depends(get_db), _=Depends(current_user)):
    row = (db.query(RawMaterial, Cpse.code).options(defer(RawMaterial.embedding))
           .join(Cpse, Cpse.id == RawMaterial.cpse_id).filter(RawMaterial.id == rid).first())
    if not row:
        raise HTTPException(404, "Legacy material not found")
    r, code = row
    m = db.query(CodeMapping).filter_by(raw_material_id=r.id).first()
    pairs = (db.query(MatchPair).filter(or_(MatchPair.a_id == r.id, MatchPair.b_id == r.id))
             .order_by(MatchPair.score.desc()).limit(30).all())
    history = (db.query(AuditLog).filter(AuditLog.entity == "legacy_code", AuditLog.entity_id == legacy_ref(r))
               .order_by(AuditLog.at.desc()).limit(30).all())
    return {**legacy_out(r, code, m.nmc if m else None), "norm_text": r.norm_text,
            "pairs": pairs_out(db, pairs), "history": [audit_out(a) for a in history]}


@router.get("/legacy/{cpse}/{code:path}")
def resolve_legacy(cpse: str, code: str, db: Session = Depends(get_db), _=Depends(current_user)):
    """Which national code does this CPSE code map to today? Follows successors of merged codes (G4, ADR-20)."""
    row = (db.query(RawMaterial, Cpse.code).options(defer(RawMaterial.embedding))
           .join(Cpse, Cpse.id == RawMaterial.cpse_id)
           .filter(Cpse.code == cpse.strip().upper(), RawMaterial.legacy_code == code.strip()).first())
    if not row:
        raise HTTPException(404, f"{cpse}/{code} is not in the material master")
    r, cpse_code = row
    m = db.query(CodeMapping).filter_by(raw_material_id=r.id).first()
    active = resolve_active(db, m.nmc) if m else None
    return {**legacy_out(r, cpse_code, m.nmc if m else None),
            "active_nmc": active.nmc if active else None,
            "standard_description": active.standard_description if active else None}
