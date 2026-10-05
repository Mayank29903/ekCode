from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ekml.embed import embed
from ekml.explain import explain
from ekml.extract import extract
from ekml.features import pair_features
from ekml.gates import gate_failures
from ekml.normalize import normalize
from ekml.score import decide
from ekml.standardize import standard_description

from ..db import get_db
from ..models import CodeMapping, Cpse, NationalMaterial, RawMaterial
from ..security import current_user
from ..services.match_service import active_model
from ..settings_store import thresholds
from .materials import legacy_out, material_out, member_stats

router = APIRouter(tags=["search"])


def _rank(hit: dict) -> tuple:
    return (bool(hit["gate_failures"]), -hit["score"])        # gate conflicts last, then best score first


@router.get("/search")
def search(q: str = Query(..., min_length=2, max_length=500), limit: int = Query(20, ge=1, le=50),
           cpse: str | None = None, db: Session = Depends(get_db), _=Depends(current_user)):
    """FR8: paste any description -> ranked national materials and unmapped legacy items, each with "why" chips.
    The first search after a restart loads the embedding model (a few seconds)."""
    norm = normalize(q)
    attrs, _conf = extract(norm)
    vec = embed([norm or q.lower()])[0]
    th = thresholds(db)
    clf, version = active_model(db)

    exact = []                                                # the text typed is itself a code
    if nm := db.get(NationalMaterial, q.strip().upper()):
        exact.append({"kind": "nmc", **material_out(nm)})
    for r, code, nmc in (db.query(RawMaterial, Cpse.code, CodeMapping.nmc)
                         .join(Cpse, Cpse.id == RawMaterial.cpse_id)
                         .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
                         .filter(RawMaterial.legacy_code == q.strip()).limit(10)):
        exact.append({"kind": "legacy", **legacy_out(r, code, nmc)})

    dist = RawMaterial.embedding.cosine_distance(vec).label("d")
    stmt = (select(RawMaterial, dist, CodeMapping.nmc, Cpse.code)
            .join(Cpse, Cpse.id == RawMaterial.cpse_id)
            .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
            .where(RawMaterial.embedding.is_not(None)))
    if cpse:
        stmt = stmt.where(Cpse.code == cpse.strip().upper())
    rows = db.execute(stmt.order_by(dist).limit(max(60, limit * 4))).all()

    national: dict[str, dict] = {}
    legacy: list[dict] = []
    for r, d, nmc, cpse_code in rows:
        sim = 1 - float(d)
        other = r.attributes or {}
        f = pair_features(sim, norm, r.norm_text or "", attrs, other, None, r.uom_code)
        gates = gate_failures(attrs, other)
        dec = decide(f, gates, th, clf)
        hit = {"score": dec.score, "match_type": dec.match_type, "gate_failures": gates,
               "explanation": explain(f, attrs, other, gates)}
        if nmc is None:
            legacy.append({**hit, **legacy_out(r, cpse_code)})
            continue
        best = national.get(nmc)
        example = {"cpse": cpse_code, "legacy_code": r.legacy_code, "description": r.description}
        if best is None or _rank(hit) < _rank(best):
            national[nmc] = {**hit, "matched": example, "matched_count": (best or {}).get("matched_count", 0) + 1}
        else:
            best["matched_count"] += 1

    if national:
        s = member_stats()
        for row in (db.query(NationalMaterial, s.c.legacy_count, s.c.cpse_count, s.c.spend, s.c.synthetic, s.c.cpses)
                    .outerjoin(s, s.c.nmc == NationalMaterial.nmc)
                    .filter(NationalMaterial.nmc.in_(list(national)))):
            national[row[0].nmc].update(material_out(*row))

    return {"query": {"text": q, "normalized": norm, "attributes": attrs,
                      "standard_description": standard_description(attrs, q)},
            "exact": exact,
            "national": sorted(national.values(), key=_rank)[:limit],
            "legacy": sorted(legacy, key=_rank)[:limit],
            "model_version": version}
