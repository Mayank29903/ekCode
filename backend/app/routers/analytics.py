from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, CodeMapping, Cpse, IngestJob, MatchPair, ModelRegistry, NationalMaterial, RawMaterial
from ..security import current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Annual spend of legacy items = unit price x annual quantity (rows missing either are ignored by SUM).
SPEND = func.coalesce(func.sum(RawMaterial.unit_price * RawMaterial.annual_qty), 0)
PAIR_STATUSES = ("suggested", "approved", "rejected", "blocked")


def _clusters():
    """Per NMC: legacy items (n), distinct CPSEs (c) and combined annual value (v)."""
    return (select(CodeMapping.nmc.label("nmc"), func.count(RawMaterial.id).label("n"),
                   func.count(distinct(RawMaterial.cpse_id)).label("c"), SPEND.label("v"))
            .join(RawMaterial, RawMaterial.id == CodeMapping.raw_material_id)
            .group_by(CodeMapping.nmc).subquery())


@router.get("/kpis")
def kpis(db: Session = Depends(get_db), _=Depends(current_user)):
    legacy_items = db.scalar(select(func.count()).select_from(RawMaterial)) or 0
    mapped = db.scalar(select(func.count()).select_from(CodeMapping)) or 0
    total_spend = float(db.scalar(select(SPEND).select_from(RawMaterial)) or 0)
    mapped_spend = float(db.scalar(select(SPEND).select_from(RawMaterial)
                                   .join(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)) or 0)
    nmc_status = dict(db.execute(select(NationalMaterial.status, func.count()).group_by(NationalMaterial.status)).all())
    pairs = dict(db.execute(select(MatchPair.status, func.count()).group_by(MatchPair.status)).all())
    cl = _clusters()
    codes_eliminated = db.scalar(select(func.coalesce(func.sum(cl.c.n - 1), 0)).select_from(cl)) or 0
    duplicate_items = db.scalar(select(func.coalesce(func.sum(cl.c.n), 0)).select_from(cl).where(cl.c.n >= 2)) or 0
    shared_count, shared_value = db.execute(select(func.count(), func.coalesce(func.sum(cl.c.v), 0))
                                            .select_from(cl).where(cl.c.c >= 2)).one()
    synthetic = db.scalar(select(func.count()).select_from(RawMaterial).where(RawMaterial.source == "synthetic")) or 0
    last_ingest = db.scalar(select(func.max(IngestJob.created_at)).where(IngestJob.status == "done"))
    return {
        "legacy_items": legacy_items,
        "cpses_onboarded": db.scalar(select(func.count(distinct(RawMaterial.cpse_id)))) or 0,
        "national_codes": nmc_status.get("active", 0),
        "deprecated_codes": nmc_status.get("deprecated", 0),
        "mapped_items": mapped,
        "unmapped_items": legacy_items - mapped,
        "mapped_pct": round(100 * mapped / legacy_items, 1) if legacy_items else 0.0,
        "pairs": {s: pairs.get(s, 0) for s in PAIR_STATUSES},
        "pending_review": pairs.get("suggested", 0),
        "duplicate_items": int(duplicate_items),          # legacy items sharing an NMC with at least one other
        "codes_eliminated": int(codes_eliminated),        # legacy codes that collapse into an existing NMC
        "total_spend": total_spend,
        "mapped_spend": mapped_spend,
        "aggregation_opportunities": shared_count,        # NMCs bought by 2+ CPSEs
        "aggregation_value": float(shared_value),
        "synthetic_items": synthetic,
        "last_ingest_at": last_ingest.isoformat() if last_ingest else None,
        "model_version": db.scalar(select(ModelRegistry.version).where(ModelRegistry.active.is_(True))) or "weighted-v1",
    }


@router.get("/by-cpse")
def by_cpse(db: Session = Depends(get_db), _=Depends(current_user)):
    cl = _clusters()
    rows = db.execute(
        select(Cpse.id, Cpse.code, Cpse.name, Cpse.sector,
               func.count(RawMaterial.id).label("items"), func.count(CodeMapping.id).label("mapped"),
               SPEND.label("spend"),
               func.count(RawMaterial.id).filter(cl.c.n >= 2).label("duplicates"),
               func.count(RawMaterial.id).filter(RawMaterial.source == "synthetic").label("synthetic"))
        .join(RawMaterial, RawMaterial.cpse_id == Cpse.id)
        .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
        .outerjoin(cl, cl.c.nmc == CodeMapping.nmc)
        .group_by(Cpse.id).order_by(func.count(RawMaterial.id).desc())).all()
    pending = dict(db.execute(
        select(RawMaterial.cpse_id, func.count(distinct(MatchPair.id)))
        .join(MatchPair, or_(MatchPair.a_id == RawMaterial.id, MatchPair.b_id == RawMaterial.id))
        .where(MatchPair.status == "suggested").group_by(RawMaterial.cpse_id)).all())
    return [{"code": r.code, "name": r.name, "sector": r.sector, "items": r.items, "mapped": r.mapped,
             "unmapped": r.items - r.mapped, "mapped_pct": round(100 * r.mapped / r.items, 1) if r.items else 0.0,
             "duplicates": r.duplicates, "synthetic": r.synthetic, "spend": float(r.spend or 0),
             "pending_review": pending.get(r.id, 0)} for r in rows]


@router.get("/categories")
def categories(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), _=Depends(current_user)):
    noun = func.coalesce(RawMaterial.attributes["noun"].astext, "UNCLASSIFIED").label("noun")
    rows = db.execute(select(noun, func.count(RawMaterial.id).label("items"),
                             func.count(CodeMapping.id).label("mapped"), SPEND.label("spend"))
                      .select_from(RawMaterial)
                      .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
                      .group_by(noun).order_by(func.count(RawMaterial.id).desc()).limit(limit)).all()
    # One expression object for SELECT and GROUP BY: with server-side parameters (psycopg 3) two separately built
    # coalesce(..., 'UNCLASSIFIED') would get different placeholders and Postgres would reject the GROUP BY.
    nm_noun = func.coalesce(NationalMaterial.noun, "UNCLASSIFIED")
    nmcs = dict(db.execute(select(nm_noun, func.count()).where(NationalMaterial.status == "active")
                           .group_by(nm_noun)).all())
    return [{"noun": r.noun, "items": r.items, "mapped": r.mapped, "spend": float(r.spend or 0),
             "national_codes": nmcs.get(r.noun, 0)} for r in rows]


@router.get("/match-types")
def match_types(db: Session = Depends(get_db), _=Depends(current_user)):
    types: dict[str, dict] = {}
    for t, s, n in db.execute(select(MatchPair.match_type, MatchPair.status, func.count())
                              .group_by(MatchPair.match_type, MatchPair.status)).all():
        row = types.setdefault(t, {"match_type": t, "total": 0, **{st: 0 for st in PAIR_STATUSES}})
        row[s] = n
        row["total"] += n
    bucket = func.least(func.width_bucket(MatchPair.score, 0.0, 1.0, 10), 10).label("bucket")
    hist = dict(db.execute(select(bucket, func.count()).where(MatchPair.status != "blocked")
                           .group_by(bucket)).all())
    gates = select(func.unnest(MatchPair.gate_failures).label("gate")).where(MatchPair.status == "blocked").subquery()
    by_gate = db.execute(select(gates.c.gate, func.count()).group_by(gates.c.gate)
                         .order_by(func.count().desc())).all()
    return {"by_type": sorted(types.values(), key=lambda r: -r["total"]),
            "score_histogram": [{"from": round((b - 1) / 10, 1), "to": round(b / 10, 1), "count": hist.get(b, 0)}
                                for b in range(1, 11)],
            "blocked_by_gate": [{"gate": g, "count": n} for g, n in by_gate]}


@router.get("/aggregation")
def aggregation(limit: int = Query(25, ge=1, le=200), min_cpses: int = Query(2, ge=2, le=20),
                db: Session = Depends(get_db), _=Depends(current_user)):
    """FR9: the same NMC bought by several CPSEs = demand that can be aggregated.
    savings_potential = what the CPSEs pay today minus what they would pay at the lowest unit price among them."""
    n_cpse = func.count(distinct(RawMaterial.cpse_id))
    priced_qty = func.coalesce(func.sum(RawMaterial.annual_qty).filter(RawMaterial.unit_price.is_not(None)), 0)
    stmt = (select(NationalMaterial.nmc, NationalMaterial.standard_description, NationalMaterial.noun,
                   func.array_agg(distinct(Cpse.code)).label("cpses"),
                   func.count(RawMaterial.id).label("legacy_count"), n_cpse.label("cpse_count"),
                   func.coalesce(func.sum(RawMaterial.annual_qty), 0).label("qty"), SPEND.label("value"),
                   func.min(RawMaterial.unit_price).label("min_price"),
                   func.max(RawMaterial.unit_price).label("max_price"), priced_qty.label("priced_qty"),
                   func.bool_and(RawMaterial.source == "synthetic").label("synthetic"))
            .join(CodeMapping, CodeMapping.nmc == NationalMaterial.nmc)
            .join(RawMaterial, RawMaterial.id == CodeMapping.raw_material_id)
            .join(Cpse, Cpse.id == RawMaterial.cpse_id)
            .where(NationalMaterial.status == "active")
            .group_by(NationalMaterial.nmc)
            .having(n_cpse >= min_cpses))
    sub = stmt.subquery()
    saving = sub.c.value - func.coalesce(sub.c.min_price, 0) * sub.c.priced_qty
    count, value, savings = db.execute(select(func.count(), func.coalesce(func.sum(sub.c.value), 0),
                                              func.coalesce(func.sum(saving), 0))).one()
    rows = db.execute(stmt.order_by(SPEND.desc(), NationalMaterial.nmc).limit(limit)).all()

    def item(r) -> dict:
        min_p = float(r.min_price) if r.min_price is not None else None
        return {"nmc": r.nmc, "standard_description": r.standard_description, "noun": r.noun,
                "cpses": sorted(r.cpses), "cpse_count": r.cpse_count, "legacy_count": r.legacy_count,
                "annual_qty": float(r.qty), "annual_value": float(r.value), "min_price": min_p,
                "max_price": float(r.max_price) if r.max_price is not None else None,
                "savings_potential": max(0.0, float(r.value) - (min_p or 0) * float(r.priced_qty)),
                "synthetic": bool(r.synthetic)}

    return {"items": [item(r) for r in rows], "total_opportunities": count, "total_value": float(value),
            "total_savings_potential": max(0.0, float(savings)), "min_cpses": min_cpses}


@router.get("/activity")
def activity(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _=Depends(current_user)):
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day = func.date_trunc("day", AuditLog.at).label("day")
    counts: dict[str, dict[str, int]] = {}
    for d, action, n in db.execute(select(day, AuditLog.action, func.count()).where(AuditLog.at >= since)
                                   .group_by(day, AuditLog.action)).all():
        counts.setdefault(d.date().isoformat(), {})[action] = n
    series = []
    for i in range(days):
        key = (since + timedelta(days=i)).date().isoformat()
        by_action = counts.get(key, {})
        series.append({"date": key, "total": sum(by_action.values()), "by_action": by_action})
    # The dashboard feed shows who did what, not the before/after payloads (those need an audit role).
    recent = [{"at": a.at.isoformat() if a.at else None, "actor_email": a.actor_email, "action": a.action,
               "entity": a.entity, "entity_id": a.entity_id}
              for a in db.query(AuditLog).order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(15)]
    jobs = [{"id": str(j.id), "cpse": code, "filename": j.filename, "status": j.status, "stage": j.stage,
             "total_rows": j.total_rows, "created_at": j.created_at.isoformat() if j.created_at else None}
            for j, code in db.query(IngestJob, Cpse.code).join(Cpse, Cpse.id == IngestJob.cpse_id)
            .order_by(IngestJob.created_at.desc()).limit(5)]
    return {"series": series, "recent": recent, "jobs": jobs}
