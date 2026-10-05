import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import write_audit
from ..config import settings
from ..db import SessionLocal, get_db
from ..models import Cpse, IngestJob, User
from ..security import authenticate, current_user, require
from ..services.ingest_service import REQUIRED, SAP_FIELDS, auto_map, read_table
from ..workers.queue import queue

router = APIRouter(prefix="/ingest", tags=["ingest"])
UPLOADERS = ("admin", "data_steward", "cpse_user")
EXTENSIONS = (".csv", ".txt", ".tsv", ".xlsx", ".xls")
_CHUNK = 1024 * 1024


ACTIVE = ("queued", "running")


def is_stale(j: IngestJob) -> bool:
    """Queued or running, but no progress for a while: the worker probably stopped. Such a job may be restarted."""
    last = j.updated_at or j.created_at
    return (j.status in ACTIVE and last is not None
            and datetime.now(timezone.utc) - last > timedelta(minutes=settings.stale_job_minutes))


def job_out(j: IngestJob) -> dict:
    return {"id": str(j.id), "filename": j.filename, "source": j.source, "status": j.status, "stage": j.stage,
            "progress": j.progress, "total_rows": j.total_rows, "processed_rows": j.processed_rows,
            "error_rows": j.error_rows, "report": j.report, "column_map": j.column_map, "stale": is_stale(j),
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None}


def _visible(user: User, job: IngestJob) -> bool:
    return user.role != "cpse_user" or job.cpse_id == user.cpse_id


def _get_job(db: Session, job_id: uuid.UUID, user: User) -> IngestJob:
    job = db.get(IngestJob, job_id)
    if not job or not _visible(user, job):
        raise HTTPException(404, "Job not found")
    return job


def _save_upload(file: UploadFile, dest: Path) -> None:
    limit, size = settings.max_upload_mb * 1024 * 1024, 0
    with dest.open("wb") as f:
        while chunk := file.file.read(_CHUNK):
            size += len(chunk)
            if size > limit:
                break
            f.write(chunk)
    if size > limit:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB")


@router.post("/upload")
def upload(file: UploadFile = File(...), cpse_code: str = Form(...), db: Session = Depends(get_db),
           user: User = Depends(require(*UPLOADERS))):
    cpse = db.query(Cpse).filter_by(code=cpse_code.strip().upper()).first()
    if not cpse:
        raise HTTPException(404, "Unknown CPSE")
    if user.role == "cpse_user" and user.cpse_id != cpse.id:
        raise HTTPException(403, "You can upload only for your own CPSE")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(400, "Upload a CSV, TSV or Excel file")
    folder = Path(settings.data_dir) / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{uuid.uuid4()}{suffix}"          # never trust the client's file name on disk
    _save_upload(file, dest)
    try:
        df = read_table(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read the file: {str(e)[:200]}") from None
    if df.empty:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "The file has a header but no rows")
    job = IngestJob(cpse_id=cpse.id, filename=(file.filename or dest.name)[:300], path=str(dest),
                    total_rows=len(df), created_by=user.id)
    db.add(job)
    db.commit()
    return {"job": job_out(job), "columns": list(df.columns), "suggested_mapping": auto_map(list(df.columns)),
            "preview": df.head(8).to_dict("records"), "bad_lines": len(df.attrs.get("bad_lines", []))}


class StartIn(BaseModel):
    mapping: dict[str, str]


@router.post("/{job_id}/start")
def start(job_id: uuid.UUID, body: StartIn, db: Session = Depends(get_db), user: User = Depends(require(*UPLOADERS))):
    job = db.query(IngestJob).filter_by(id=job_id).with_for_update().first()   # two clicks cannot queue it twice
    if not job or not _visible(user, job):
        raise HTTPException(404, "Job not found")
    if job.status in ACTIVE and not is_stale(job):
        raise HTTPException(409, "This file is already being processed")
    if not job.path or not Path(job.path).exists():
        raise HTTPException(410, "The uploaded file is no longer on the server. Upload it again.")
    mapping = {k: v for k, v in body.mapping.items() if k in SAP_FIELDS and v}
    missing = [f for f in REQUIRED if not mapping.get(f)]
    if missing:
        raise HTTPException(422, f"Map required fields: {', '.join(missing)}")
    try:
        columns = set(read_table(Path(job.path), nrows=0).columns)
    except Exception as e:
        raise HTTPException(400, f"Could not read the file: {str(e)[:200]}") from None
    if unknown := [v for v in mapping.values() if v not in columns]:
        raise HTTPException(422, f"Columns not found in the file: {', '.join(unknown)}")
    restart = job.status in ACTIVE
    job.column_map, job.status, job.stage, job.progress = mapping, "queued", "queued", 0
    job.report = None
    write_audit(db, user, "ingest", "ingest_job", job.id, None, {"file": job.filename, "rows": job.total_rows},
                "restarted after the job stalled" if restart else None)
    db.commit()
    try:
        queue.enqueue("app.workers.jobs.ingest_job", str(job.id), job_timeout=7200)
    except Exception:
        job.status, job.stage = "error", "error"
        job.report = {"error": "The job queue (Redis) is unavailable. Try again in a moment."}
        db.commit()
        raise HTTPException(503, "Job queue unavailable") from None
    return job_out(job)


@router.get("/jobs")
def jobs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(IngestJob)
    if user.role == "cpse_user":
        q = q.filter(IngestJob.cpse_id == user.cpse_id)
    return [job_out(j) for j in q.order_by(IngestJob.created_at.desc()).limit(20)]


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return job_out(_get_job(db, job_id, user))


@router.get("/{job_id}/events")
async def events(job_id: uuid.UUID, request: Request, user: User = Depends(authenticate)):
    """SSE progress stream. Each poll opens a short session, so an open stream holds no pooled connection."""
    def read():
        with SessionLocal() as db:
            j = db.get(IngestJob, job_id)
            return job_out(j) if j and _visible(user, j) else None

    first = await run_in_threadpool(read)
    if first is None:                    # a 404 (not an empty stream) stops EventSource from reconnecting forever
        raise HTTPException(404, "Job not found")

    async def stream():
        data, last, last_sent = first, None, time.monotonic()
        while not await request.is_disconnected():
            if data is None:
                break
            if data != last:
                yield f"data: {json.dumps(data)}\n\n"
                last, last_sent = data, time.monotonic()
            elif time.monotonic() - last_sent > 15:
                yield ": keep-alive\n\n"
                last_sent = time.monotonic()
            if data["status"] in ("done", "error", "uploaded"):    # nothing more will happen on this stream
                break
            await asyncio.sleep(0.7)
            data = await run_in_threadpool(read)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
