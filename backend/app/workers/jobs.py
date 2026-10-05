import traceback
from pathlib import Path

from ekml.score import decide
from ekml.train import train

from ..config import settings
from ..db import SessionLocal
from ..models import IngestJob, MatchPair, ModelRegistry, RawMaterial
from ..services.ingest_service import run_pipeline
from ..settings_store import get_setting, thresholds


def _load_dictionary(db) -> None:
    """The worker lives across jobs, so reload the steward's dictionary every time (an empty one = the YAML seed,
    which also undoes a reset made since the last job)."""
    from ekml.normalize import set_abbreviations
    set_abbreviations(get_setting(db, "abbreviations"))


def _fail(db, job_id: str, e: Exception) -> None:
    """Surface every failure to the UI (job row), then let RQ record the traceback too."""
    db.rollback()
    job = db.get(IngestJob, job_id)
    if job is None:
        return
    job.status, job.stage = "error", "error"
    job.report = {**(job.report or {}), "error": str(e)[:500], "trace": traceback.format_exc()[-2000:]}
    db.commit()


def ingest_job(job_id: str):
    with SessionLocal() as db:
        _load_dictionary(db)
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        try:
            run_pipeline(db, job)
        except Exception as e:
            _fail(db, job_id, e)
            raise


def sap_pull_job(job_id: str, top: int = 200, base_url: str | None = None, api_key: str | None = None):
    """FR12: pull products from SAP OData into a CSV, then run the same pipeline as a file upload."""
    from ..services.sap_service import pull_products
    with SessionLocal() as db:
        _load_dictionary(db)
        job = db.get(IngestJob, job_id)
        if job is None:
            return
        try:
            job.status, job.stage, job.progress = "running", "parsing", 0
            db.commit()
            df = pull_products(base_url or settings.sap_base_url, api_key or settings.sap_api_key, top)
            folder = Path(settings.data_dir) / "uploads"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"sap_{job.id}.csv"
            df.to_csv(path, index=False)
            job.path, job.total_rows = str(path), len(df)
            db.commit()
            run_pipeline(db, job)
        except Exception as e:
            _fail(db, job_id, e)
            raise


def retrain_job():
    """Labels: approved = 1; rejected and gate-blocked = 0 (blocked pairs are confirmed different materials)."""
    with SessionLocal() as db:
        pairs = db.query(MatchPair).filter(MatchPair.status.in_(["approved", "rejected", "blocked"])).all()
        rows = [(p.features, 1 if p.status == "approved" else 0) for p in pairs if p.features]
        res = train(rows, Path(settings.data_dir) / "models")
        db.add(ModelRegistry(version=res["version"], path=res["path"], metrics=res["metrics"], active=False))
        db.commit()
        return res


def rescore_job():
    """Re-score open suggestions from their stored features with the current thresholds and active model.
    Cheap (no re-embedding); run it after changing thresholds or activating a model."""
    from ..services.match_service import active_model
    with SessionLocal() as db:
        th = thresholds(db)
        clf, version = active_model(db)
        pairs = db.query(MatchPair).filter(MatchPair.status == "suggested").all()
        ids = {i for p in pairs for i in (p.a_id, p.b_id)}
        spend = {rid: float(price or 0) * float(qty or 0) for rid, price, qty in
                 db.query(RawMaterial.id, RawMaterial.unit_price, RawMaterial.annual_qty)
                 .filter(RawMaterial.id.in_(ids))} if ids else {}
        for p in pairs:
            if not p.features:
                continue
            dec = decide(p.features, [], th, clf)
            uncertainty = max(0.0, 1 - abs(dec.score - th["near"]))
            p.score, p.match_type, p.model_version = dec.score, dec.match_type, version
            p.impact = round((spend.get(p.a_id, 0) + spend.get(p.b_id, 0)) * uncertainty + dec.score, 2)
        db.commit()
        return {"rescored": len(pairs), "model_version": version}
