from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ekml.gates import gate_failures

from ..audit import write_audit
from ..models import CodeMapping, MatchPair, NationalMaterial, RawMaterial
from .nmc_service import issue_nmc


def legacy_ref(r: RawMaterial) -> str:
    return f"{r.cpse_id}:{r.legacy_code}"


def resolve_active(db: Session, nmc: str) -> NationalMaterial | None:
    """Follow successor_nmc from a deprecated code to the active one (ADR-20)."""
    nm, seen = db.get(NationalMaterial, nmc), set()
    while nm is not None and nm.status == "deprecated" and nm.successor_nmc and nm.nmc not in seen:
        seen.add(nm.nmc)
        nm = db.get(NationalMaterial, nm.successor_nmc)
    return nm


def mapping_of(db: Session, rid: int) -> CodeMapping | None:
    return db.query(CodeMapping).filter_by(raw_material_id=rid).first()


def lock_materials(db: Session, *ids: int) -> dict[int, RawMaterial]:
    """Row locks taken in id order (no deadlocks), so two approvals touching one material run one after the other."""
    rows = db.query(RawMaterial).filter(RawMaterial.id.in_(ids)).order_by(RawMaterial.id).with_for_update().all()
    return {r.id: r for r in rows}


def map_to(db: Session, r: RawMaterial, nmc: str, conf: float, user):
    m = mapping_of(db, r.id)
    before = {"nmc": m.nmc} if m else None
    if m:
        m.nmc, m.confidence = nmc, conf
    else:
        db.add(CodeMapping(raw_material_id=r.id, nmc=nmc, confidence=conf, status="approved",
                           approved_by=getattr(user, "id", None)))
    r.status = "mapped"
    write_audit(db, user, "map", "legacy_code", legacy_ref(r), before, {"nmc": nmc})


def merge(db: Session, keep: str, drop: str, user) -> str:
    k, d = db.get(NationalMaterial, keep), db.get(NationalMaterial, drop)
    if (k.created_at, k.nmc) > (d.created_at, d.nmc):
        k, d = d, k                                         # the older code survives (FLOW §4)
    if conflicts := gate_failures(k.attributes or {}, d.attributes or {}):
        raise HTTPException(409, f"Cannot merge: {', '.join(conflicts)} differ between {k.nmc} and {d.nmc}")
    for m in db.query(CodeMapping).filter_by(nmc=d.nmc).all():   # every remapped legacy code is audited (G4)
        m.nmc = k.nmc
        write_audit(db, user, "remap", "legacy_code", legacy_ref(db.get(RawMaterial, m.raw_material_id)),
                    {"nmc": d.nmc}, {"nmc": k.nmc}, f"{d.nmc} merged into {k.nmc}")
    d.status, d.successor_nmc = "deprecated", k.nmc
    write_audit(db, user, "merge", "national_material", d.nmc, {"status": "active"},
                {"status": "deprecated", "successor": k.nmc})
    return k.nmc


def approve_pair(db: Session, p: MatchPair | None, user, reason: str | None = None) -> str:
    """The approve transaction (FLOW §4). The caller locks the pair row and commits."""
    if p is None:
        raise HTTPException(404, "Pair not found")
    if p.status != "suggested":
        raise HTTPException(409, f"Pair already {p.status}")
    mats = lock_materials(db, p.a_id, p.b_id)
    a, b = mats[p.a_id], mats[p.b_id]
    ma, mb = mapping_of(db, a.id), mapping_of(db, b.id)
    if ma and mb:
        nmc = ma.nmc if ma.nmc == mb.nmc else merge(db, ma.nmc, mb.nmc, user)
    elif ma or mb:
        nmc = (ma or mb).nmc
        map_to(db, b if ma else a, nmc, p.score, user)
    else:
        nm = issue_nmc(db, [a, b])
        nmc = nm.nmc
        write_audit(db, user, "create", "national_material", nmc, None,
                    {"description": nm.standard_description, "attributes": nm.attributes})
        map_to(db, a, nmc, p.score, user)
        map_to(db, b, nmc, p.score, user)
    p.status, p.decided_by, p.decided_at = "approved", getattr(user, "id", None), datetime.now(timezone.utc)
    write_audit(db, user, "approve", "match_pair", p.id, {"status": "suggested"}, {"status": "approved", "nmc": nmc},
                reason)
    return nmc


def reject_pair(db: Session, p: MatchPair | None, user, reason: str | None = None):
    if p is None:
        raise HTTPException(404, "Pair not found")
    if p.status != "suggested":
        raise HTTPException(409, f"Pair already {p.status}")
    p.status, p.decided_by, p.decided_at = "rejected", getattr(user, "id", None), datetime.now(timezone.utc)
    write_audit(db, user, "reject", "match_pair", p.id, {"status": "suggested"}, {"status": "rejected"}, reason)


PROMOTE_LOCK = 0x454B434F  # "EKCO": one "issue codes for unique materials" run at a time


def promote_singletons(db: Session, user) -> int:
    """Issue codes for unique materials: every processed material with no mapping and no open suggestion.
    Serialised with an advisory lock, so two stewards clicking at once cannot both issue a code for one row."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PROMOTE_LOCK})
    pending_ids = {i for p in db.query(MatchPair.a_id, MatchPair.b_id).filter_by(status="suggested") for i in p}
    mapped = {r for (r,) in db.query(CodeMapping.raw_material_id)}
    rows = db.query(RawMaterial).filter(RawMaterial.status.in_(["matched", "embedded"])).all()
    n = 0
    for r in rows:
        if r.id in mapped or r.id in pending_ids:
            continue
        nm = issue_nmc(db, [r])
        write_audit(db, user, "create", "national_material", nm.nmc, None,
                    {"description": nm.standard_description, "singleton": True})
        map_to(db, r, nm.nmc, 1.0, user)
        n += 1
    db.commit()
    return n
