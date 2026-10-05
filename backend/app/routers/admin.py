import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy import func
from sqlalchemy.orm import Session

from ekml import MIN_PER_CLASS, MIN_ROWS
from ekml.embed import model_name
from ekml.extract import extract
from ekml.llm import provider
from ekml.normalize import normalize, seed_abbreviations, set_abbreviations
from ekml.standardize import standard_description

from ..audit import write_audit
from ..db import get_db
from ..models import Cpse, MatchPair, ModelRegistry, Setting, User
from ..security import hash_password, require, set_session
from ..settings_store import flags, get_setting, put_setting, thresholds
from ..workers.queue import queue

router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN = ("admin",)
READERS = ("admin", "data_steward", "auditor")
Role = Literal["admin", "data_steward", "cpse_user", "auditor"]
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


# ---- runtime settings (thresholds + flags) -----------------------------------------------------------------------

class Thresholds(BaseModel):
    review_floor: float = Field(ge=0, le=1)
    equivalent: float = Field(ge=0, le=1)
    near: float = Field(ge=0, le=1)
    auto_suggest: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if not self.review_floor <= self.equivalent <= self.near <= self.auto_suggest:
            raise ValueError("thresholds must satisfy review_floor <= equivalent <= near <= auto_suggest")
        return self


class Flags(BaseModel):
    auto_approve_exact: bool
    use_llm: bool


class SettingsIn(BaseModel):
    thresholds: Thresholds | None = None
    flags: Flags | None = None


def _settings(db: Session) -> dict:
    return {"thresholds": thresholds(db), "flags": flags(db), "llm_provider": provider(), "embed_model": model_name()}


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), _=Depends(require(*READERS))):
    return _settings(db)


@router.put("/settings")
def write_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    """New thresholds apply to new matches; POST /admin/rescore re-classifies open suggestions."""
    current = {"thresholds": thresholds(db), "flags": flags(db)}
    for key, model in (("thresholds", body.thresholds), ("flags", body.flags)):
        if model is None:
            continue
        before, after = current[key], model.model_dump()
        if before != after:
            put_setting(db, key, after)
            write_audit(db, user, "update", "setting", key, before, after)
    db.commit()
    return _settings(db)


# ---- abbreviation dictionary (FR2) -------------------------------------------------------------------------------

class DictionaryIn(BaseModel):
    abbreviations: dict[str, str]

    @field_validator("abbreviations")
    @classmethod
    def clean(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 5000:
            raise ValueError("at most 5000 entries")
        out = {}
        for k, val in v.items():
            k, val = k.strip().lower(), " ".join(str(val).split()).lower()
            if not k or " " in k or len(k) > 30:
                raise ValueError(f"abbreviation {k!r} must be one word of at most 30 characters")
            if not val or len(val) > 60:
                raise ValueError(f"expansion for {k!r} must be 1-60 characters")
            out[k] = val
        return out


def _diff(before: dict, after: dict) -> dict:
    return {"added": {k: after[k] for k in after.keys() - before.keys()},
            "removed": sorted(before.keys() - after.keys()),
            "changed": {k: [before[k], after[k]] for k in after.keys() & before.keys() if before[k] != after[k]}}


@router.get("/dictionary")
def read_dictionary(db: Session = Depends(get_db), _=Depends(require(*READERS))):
    saved = get_setting(db, "abbreviations")
    return {"abbreviations": dict(sorted((saved or seed_abbreviations()).items())), "custom": bool(saved)}


@router.put("/dictionary")
def write_dictionary(body: DictionaryIn, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    """Takes effect for new uploads immediately (the worker reloads it per job) and for search in this API."""
    before = get_setting(db, "abbreviations") or seed_abbreviations()
    put_setting(db, "abbreviations", body.abbreviations)
    write_audit(db, user, "update", "setting", "abbreviations", None, _diff(before, body.abbreviations))
    db.commit()
    set_abbreviations(body.abbreviations)
    return {"abbreviations": dict(sorted(body.abbreviations.items())), "custom": True}


@router.post("/dictionary/reset")
def reset_dictionary(db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    if s := db.get(Setting, "abbreviations"):
        write_audit(db, user, "reset", "setting", "abbreviations", None, {"entries": len(s.value or {})})
        db.delete(s)
        db.commit()
    set_abbreviations({})                              # empty override -> the YAML seed is used
    return {"abbreviations": dict(sorted(seed_abbreviations().items())), "custom": False}


@router.get("/preview")
def preview(text: str = Query(..., min_length=1, max_length=500), _=Depends(require(*READERS))):
    """Try the dictionary and extractor on any description (Settings → Dictionary 'try it')."""
    norm = normalize(text)
    attrs, conf = extract(norm)
    return {"text": text, "normalized": norm, "attributes": attrs, "confidence": conf,
            "standard_description": standard_description(attrs, text)}


# ---- users -------------------------------------------------------------------------------------------------------

class UserIn(BaseModel):
    email: str = Field(max_length=200)
    name: str = Field(min_length=2, max_length=120)
    role: Role
    cpse_code: str | None = None
    password: str = Field(min_length=10, max_length=200)

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("not an email address")
        return v


class UserPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    role: Role | None = None
    cpse_code: str | None = None                      # "" clears it
    password: str | None = Field(None, min_length=10, max_length=200)


def _user_out(u: User, cpse_codes: dict[int, str]) -> dict:
    return {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role,
            "cpse": cpse_codes.get(u.cpse_id) if u.cpse_id else None,
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _cpse_id(db: Session, code: str | None) -> int | None:
    if not code:
        return None
    c = db.query(Cpse).filter_by(code=code.strip().upper()).first()
    if not c:
        raise HTTPException(422, f"Unknown CPSE {code}")
    return c.id


@router.get("/users")
def list_users(db: Session = Depends(get_db), _=Depends(require(*ADMIN))):
    codes = dict(db.query(Cpse.id, Cpse.code))
    return [_user_out(u, codes) for u in db.query(User).order_by(User.created_at)]


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    if db.query(User).filter_by(email=body.email).first():
        raise HTTPException(409, "A user with this email already exists")
    cpse_id = _cpse_id(db, body.cpse_code)
    if body.role == "cpse_user" and not cpse_id:
        raise HTTPException(422, "A CPSE user needs a CPSE")
    u = User(email=body.email, name=body.name.strip(), role=body.role, cpse_id=cpse_id,
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    write_audit(db, user, "create", "user", u.id, None,
                {"email": u.email, "role": u.role, "cpse": body.cpse_code})     # never the password
    db.commit()
    return _user_out(u, dict(db.query(Cpse.id, Cpse.code)))


@router.patch("/users/{user_id}")
def update_user(user_id: uuid.UUID, body: UserPatch, resp: Response, db: Session = Depends(get_db),
                user: User = Depends(require(*ADMIN))):
    """A new password signs the user out everywhere (security.session_version), except this admin's own browser."""
    u = db.query(User).filter_by(id=user_id).with_for_update().first()
    if not u:
        raise HTTPException(404, "User not found")
    before = {"name": u.name, "role": u.role, "cpse_id": u.cpse_id}
    if body.role is not None and body.role != "admin" and u.role == "admin":
        if u.id == user.id:
            raise HTTPException(409, "You cannot remove your own admin role")
        if db.query(func.count()).select_from(User).filter(User.role == "admin").scalar() <= 1:
            raise HTTPException(409, "At least one admin must remain")
    if body.name is not None:
        u.name = body.name.strip()
    if body.role is not None:
        u.role = body.role
    if body.cpse_code is not None:
        u.cpse_id = _cpse_id(db, body.cpse_code)
    if u.role == "cpse_user" and not u.cpse_id:
        raise HTTPException(422, "A CPSE user needs a CPSE")
    after = {"name": u.name, "role": u.role, "cpse_id": u.cpse_id}
    if body.password:
        u.password_hash = hash_password(body.password)
        after["password"] = "changed"
    write_audit(db, user, "update", "user", u.id, before, after)
    db.commit()
    if body.password and u.id == user.id:
        set_session(resp, u)
    return _user_out(u, dict(db.query(Cpse.id, Cpse.code)))


# ---- continuous learning (FR13) ----------------------------------------------------------------------------------

def _labels(db: Session) -> dict:
    counts = dict(db.query(MatchPair.status, func.count())
                  .filter(MatchPair.status.in_(["approved", "rejected", "blocked"])).group_by(MatchPair.status).all())
    pos, neg = counts.get("approved", 0), counts.get("rejected", 0) + counts.get("blocked", 0)
    return {"approved": counts.get("approved", 0), "rejected": counts.get("rejected", 0),
            "blocked": counts.get("blocked", 0), "positives": pos, "negatives": neg,
            "min_rows": MIN_ROWS, "min_per_class": MIN_PER_CLASS,
            "ready": pos + neg >= MIN_ROWS and min(pos, neg) >= MIN_PER_CLASS}


def _model_out(m: ModelRegistry) -> dict:
    return {"version": m.version, "metrics": m.metrics, "active": m.active,
            "created_at": m.created_at.isoformat() if m.created_at else None}


@router.get("/models")
def models(db: Session = Depends(get_db), _=Depends(require(*READERS))):
    items = db.query(ModelRegistry).order_by(ModelRegistry.created_at.desc()).all()
    active = next((m.version for m in items if m.active), None)
    return {"items": [_model_out(m) for m in items], "active": active or "weighted-v1", "labels": _labels(db)}


@router.post("/retrain")
def retrain(db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    labels = _labels(db)
    if not labels["ready"]:
        raise HTTPException(409, f"Not enough decisions yet: need {MIN_ROWS} labelled pairs with at least "
                                 f"{MIN_PER_CLASS} of each kind (have {labels['positives']} approved, "
                                 f"{labels['negatives']} rejected/blocked)")
    try:
        job = queue.enqueue("app.workers.jobs.retrain_job", job_timeout=3600)
    except Exception:
        raise HTTPException(503, "Job queue unavailable") from None
    write_audit(db, user, "retrain", "model_registry", job.id, None, {"labels": labels})
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _=Depends(require(*READERS))):
    """Status of a queued background job (retrain, rescore)."""
    try:
        job = Job.fetch(job_id, connection=queue.connection)
    except NoSuchJobError:
        raise HTTPException(404, "Job not found (finished jobs expire after a while)") from None
    raw = job.get_status(refresh=True)
    status = getattr(raw, "value", raw)                # JobStatus enum -> "queued" | "started" | "finished" | ...
    out = {"job_id": job_id, "status": status, "result": None, "error": None}
    if status == "finished":
        out["result"] = job.return_value()
    elif status == "failed" and (latest := job.latest_result()):
        out["error"] = (latest.exc_string or "")[-1500:]
    return out


@router.post("/models/{version}/activate")
def activate(version: str, db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    m = db.query(ModelRegistry).filter_by(version=version).with_for_update().first()
    if not m:
        raise HTTPException(404, "Model not found")
    previous = db.query(ModelRegistry.version).filter(ModelRegistry.active.is_(True)).scalar()
    db.query(ModelRegistry).update({ModelRegistry.active: False})
    m.active = True
    write_audit(db, user, "activate", "model_registry", version, {"active": previous or "weighted-v1"},
                {"active": version})
    db.commit()
    return {"active": version}


@router.post("/models/deactivate")
def deactivate(db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    """Roll back to the weighted cold-start formula."""
    previous = db.query(ModelRegistry.version).filter(ModelRegistry.active.is_(True)).scalar()
    db.query(ModelRegistry).update({ModelRegistry.active: False})
    write_audit(db, user, "activate", "model_registry", "weighted-v1", {"active": previous}, {"active": "weighted-v1"})
    db.commit()
    return {"active": "weighted-v1"}


@router.post("/rescore")
def rescore(db: Session = Depends(get_db), user: User = Depends(require(*ADMIN))):
    """Re-classify open suggestions with the current thresholds and model (no re-embedding)."""
    try:
        job = queue.enqueue("app.workers.jobs.rescore_job", job_timeout=3600)
    except Exception:
        raise HTTPException(503, "Job queue unavailable") from None
    write_audit(db, user, "rescore", "match_pair", "suggested", None, {"job": job.id})
    db.commit()
    return {"job_id": job.id, "status": "queued"}
