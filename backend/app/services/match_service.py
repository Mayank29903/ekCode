import logging

import joblib
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ekml.explain import explain
from ekml.features import pair_features
from ekml.gates import gate_failures
from ekml.score import decide

from ..models import MatchPair, ModelRegistry, RawMaterial
from ..settings_store import flags, thresholds

log = logging.getLogger(__name__)
_MODEL = {"version": None, "clf": None}
KEEP_BLOCKED_ABOVE = 0.90   # store only convincing hard negatives, so the "Blocked" tab stays meaningful
UPDATABLE = ("score", "match_type", "features", "explanation", "gate_failures", "status", "model_version", "impact")


def active_model(db: Session):
    """The active LightGBM model, or (None, "weighted-v1"). A missing or unreadable file never stops scoring."""
    m = db.query(ModelRegistry).filter_by(active=True).first()
    if not m:
        return None, "weighted-v1"
    if _MODEL["version"] != m.version:
        try:
            _MODEL.update(version=m.version, clf=joblib.load(m.path))
        except Exception as e:  # missing file, other LightGBM version, corrupt pickle
            log.warning("cannot load model %s from %s (%s); using the weighted formula", m.version, m.path, e)
            return None, "weighted-v1"
    return _MODEL["clf"], m.version


def _spend(r: RawMaterial) -> float:
    return float(r.unit_price or 0) * float(r.annual_qty or 0)


def _upsert_pair(db: Session, values: dict) -> None:
    stmt = insert(MatchPair).values(**values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=["a_id", "b_id"],
        set_={k: stmt.excluded[k] for k in UPDATABLE},
        where=MatchPair.status.in_(["suggested", "blocked"])))    # never overwrite a steward's decision


def _release_materials(db: Session) -> None:
    for o in [o for o in db.identity_map.values() if isinstance(o, RawMaterial)]:
        db.expunge(o)


# Blocking keys: an item with the same noun and the same sizes is a candidate however it is worded.
# Grade is left out on purpose, so "SS" without a grade still meets "SS304".
BLOCK_KEYS = ("noun", "thread", "length_mm", "size_in", "rating", "schedule", "bearing_no", "cores", "area_sqmm")


def candidates(db: Session, a: RawMaterial, k: int) -> list[tuple[RawMaterial, float]]:
    """Top-k by meaning (pgvector ANN) plus top-k with the same noun and sizes (JSONB containment, GIN index).
    Embeddings barely see numbers, so with many look-alike bolts the true twin written in another style can
    fall outside the ANN top-k; attribute blocking brings it back."""
    dist = RawMaterial.embedding.cosine_distance(a.embedding).label("d")
    base = select(RawMaterial, dist).where(RawMaterial.id != a.id, RawMaterial.embedding.is_not(None))
    found = {b.id: (b, float(d)) for b, d in db.execute(base.order_by(dist).limit(k)).all()}
    block = {key: v for key, v in (a.attributes or {}).items() if key in BLOCK_KEYS}
    if "noun" in block and len(block) >= 2:
        for b, d in db.execute(base.where(RawMaterial.attributes.contains(block)).order_by(dist).limit(k)).all():
            found.setdefault(b.id, (b, float(d)))
    return list(found.values())


def match_materials(db: Session, ids: list[int], k: int = 15, on_progress=None) -> int:
    th = thresholds(db)
    auto_exact = flags(db)["auto_approve_exact"]
    clf, version = active_model(db)
    created, seen = 0, set()
    for n, mid in enumerate(ids):
        a = db.get(RawMaterial, mid)
        if a is None or a.embedding is None:
            continue
        for b, d in candidates(db, a, k):
            lo, hi = sorted((a, b), key=lambda r: r.id)
            if (lo.id, hi.id) in seen:                  # already scored from the other side in this run
                continue
            seen.add((lo.id, hi.id))
            sim = 1 - float(d)
            f = pair_features(sim, a.norm_text or "", b.norm_text or "", a.attributes or {}, b.attributes or {},
                              a.uom_code, b.uom_code)
            gates = gate_failures(a.attributes or {}, b.attributes or {})
            dec = decide(f, gates, th, clf)
            if gates and sim < KEEP_BLOCKED_ABOVE:
                continue
            if not gates and dec.score < th["review_floor"]:
                continue
            uncertainty = max(0.0, 1 - abs(dec.score - th["near"]))   # highest at the decision boundary
            _upsert_pair(db, dict(
                a_id=lo.id, b_id=hi.id, score=dec.score, match_type=dec.match_type, features=f,
                explanation=explain(f, lo.attributes or {}, hi.attributes or {}, gates),
                gate_failures=gates, status="blocked" if gates else "suggested", model_version=version,
                impact=round((_spend(a) + _spend(b)) * uncertainty + dec.score, 2)))
            created += 1
        if a.status in ("ingested", "embedded"):
            a.status = "matched"
        if n % 25 == 0 or n == len(ids) - 1:
            db.commit()
            _release_materials(db)
            if on_progress:
                on_progress((n + 1) / max(len(ids), 1))
    db.commit()
    if auto_exact:
        auto_approve_exact(db, th)
    return created


def auto_approve_exact(db: Session, th: dict) -> int:
    """ADR-19: opt-in. Only gate-clean EXACT_DUPLICATE pairs above the auto threshold, audited as `system`."""
    from ..workers.queue import enqueue_safely
    from .cluster_service import approve_pair
    floor = th.get("auto_suggest", 0.93)
    ids = [pid for (pid,) in db.query(MatchPair.id).filter(
        MatchPair.status == "suggested", MatchPair.match_type == "EXACT_DUPLICATE", MatchPair.score >= floor)]
    n = 0
    for pid in ids:
        try:
            p = db.query(MatchPair).filter_by(id=pid).with_for_update().first()
            nmc = approve_pair(db, p, None, reason="auto-approved exact duplicate")
            db.commit()
        except HTTPException as e:              # e.g. merge conflict: leave it for a steward
            db.rollback()
            log.info("auto-approve skipped pair %s: %s", pid, e.detail)
            continue
        except SQLAlchemyError as e:            # a steward decided the same pair at the same moment
            db.rollback()
            log.info("auto-approve skipped pair %s: %s", pid, e)
            continue
        n += 1
        enqueue_safely("app.services.webhook_service.deliver", "mapping.approved", {"pair": pid, "nmc": nmc})
    return n
