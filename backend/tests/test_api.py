"""End-to-end API tests against a real PostgreSQL (the docker compose `db`, or the CI service).

The RQ queue is swapped for an in-process call, so no worker is needed; the embedding model is downloaded on the
first run. Legacy codes carry a random prefix, so the tests never touch existing rows, but they do add a few rows
to the database they run against: point DATABASE_URL at a scratch database if that matters.
Set EKCODE_SKIP_PIPELINE=1 to skip the tests that need the embedding model.
"""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from app import init_db
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, CodeMapping, MatchPair, RawMaterial
from app.workers import queue as queue_module
from ekml.gates import gate_failures
from ekml.nmc import is_valid

API = "/api/v1"
RUN = uuid.uuid4().hex[:6].upper()
HEADER = "Material,Material Description,Base Unit,Unit Price,Annual Qty\n"
IOCL_CSV = (HEADER
            + f"{RUN}-IO1,HEX BOLT M12X50 SS304,NOS,42,500\n"
            + f'{RUN}-IO2,"GATE VALVE 2"" 150# A105 API 600",NOS,18500,40\n'
            + f"{RUN}-IO3,SPIRAL WOUND GASKET 4 IN 300# SS316 ASME B16.20,NOS,950,300\n")
ONGC_CSV = (HEADER
            + f"{RUN}-ON1,SS HX BLT M12 L50,EA,40,300\n"
            + f"{RUN}-ON2,HEX BOLT M16X50 SS304,NOS,55,200\n"
            + f"{RUN}-ON3,GV 2 IN 150# A105 API 600,NOS,18000,25\n"
            + f"{RUN}-ON4,GV 2 IN 300# A105 API 600,NOS,24000,10\n")
needs_pipeline = pytest.mark.skipif(os.getenv("EKCODE_SKIP_PIPELINE") == "1", reason="EKCODE_SKIP_PIPELINE=1")


def code(suffix: str) -> str:
    return f"{RUN}-{suffix}"


def pair(a: str, b: str) -> MatchPair | None:
    with SessionLocal() as db:
        ids = dict(db.query(RawMaterial.legacy_code, RawMaterial.id)
                   .filter(RawMaterial.legacy_code.in_([code(a), code(b)])))
        if len(ids) < 2:
            return None
        lo, hi = sorted((ids[code(a)], ids[code(b)]))
        return db.query(MatchPair).filter_by(a_id=lo, b_id=hi).first()


def stored_attributes(suffix: str) -> dict:
    with SessionLocal() as db:
        return db.query(RawMaterial.attributes).filter(RawMaterial.legacy_code == code(suffix)).scalar() or {}


@pytest.fixture(scope="module")
def client():
    init_db.main()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin(client):
    r = client.post(f"{API}/auth/login", json={"email": settings.admin_email, "password": settings.admin_password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def anon(client):
    return TestClient(app)          # no cookies; the app is already started by `client`


@pytest.fixture(scope="module")
def ingested(admin):
    """Upload both sample files and run the real pipeline in-process instead of on the worker."""
    from app.workers.jobs import ingest_job

    def run_now(func, *args, **kwargs):
        if func == "app.workers.jobs.ingest_job":
            ingest_job(*args)

    jobs = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(queue_module.queue, "enqueue", run_now)
        for cpse, text in (("IOCL", IOCL_CSV), ("ONGC", ONGC_CSV)):
            r = admin.post(f"{API}/ingest/upload", data={"cpse_code": cpse},
                           files={"file": (f"{cpse}.csv", text.encode(), "text/csv")})
            assert r.status_code == 200, r.text
            up = r.json()
            assert up["suggested_mapping"]["MATNR"] == "Material"
            assert up["suggested_mapping"]["MAKTX"] == "Material Description"
            r = admin.post(f"{API}/ingest/{up['job']['id']}/start", json={"mapping": up["suggested_mapping"]})
            assert r.status_code == 200, r.text
            jobs[cpse] = admin.get(f"{API}/ingest/{up['job']['id']}").json()
            assert jobs[cpse]["status"] == "done", jobs[cpse]
    return jobs


@pytest.fixture(scope="module")
def approved(ingested, admin) -> str:
    p = pair("IO1", "ON1")
    assert p is not None, "the two M12x50 bolts were never paired"
    if p.status == "suggested":
        r = admin.post(f"{API}/review/{p.id}/decision", json={"decision": "approve", "reason": "pytest"})
        assert r.status_code == 200, r.text
        return r.json()["nmc"]
    with SessionLocal() as db:
        rid = db.query(RawMaterial.id).filter(RawMaterial.legacy_code == code("IO1")).scalar()
        return db.query(CodeMapping.nmc).filter(CodeMapping.raw_material_id == rid).scalar()


# ---- auth --------------------------------------------------------------------------------------------------------

def test_health(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_protected_routes_need_a_session(anon):
    assert anon.get(f"{API}/auth/me").status_code == 401
    assert anon.get(f"{API}/review/queue").status_code == 401
    assert anon.get(f"{API}/materials").status_code == 401


def test_wrong_password_is_rejected(anon):
    r = anon.post(f"{API}/auth/login", json={"email": settings.admin_email, "password": "not-the-password"})
    assert r.status_code == 401


def test_admin_session(admin):
    r = admin.get(f"{API}/auth/me")
    me = r.json()
    assert me["role"] == "admin" and me["email"] == settings.admin_email.strip().lower()
    assert r.headers["cache-control"] == "no-store"          # authenticated JSON is never cached
    assert {"IOCL", "ONGC"} <= {c["code"] for c in admin.get(f"{API}/cpses").json()}


def test_password_change_revokes_other_sessions(admin):
    email = f"pw-{RUN.lower()}@example.com"
    r = admin.post(f"{API}/admin/users", json={"email": email, "name": "Password Test", "role": "auditor",
                                               "password": "First-Pass-2026"})
    assert r.status_code == 200, r.text
    first, second = TestClient(app), TestClient(app)
    for c in (first, second):
        assert c.post(f"{API}/auth/login", json={"email": email, "password": "First-Pass-2026"}).status_code == 200
    wrong = {"current_password": "Not-The-Password", "new_password": "Second-Pass-2026"}
    assert first.post(f"{API}/auth/password", json=wrong).status_code == 400
    good = {"current_password": "First-Pass-2026", "new_password": "Second-Pass-2026"}
    assert first.post(f"{API}/auth/password", json=good).status_code == 200
    assert first.get(f"{API}/auth/me").status_code == 200    # this browser received a fresh session
    assert second.get(f"{API}/auth/me").status_code == 401   # every other session was revoked
    fresh = TestClient(app)
    assert fresh.post(f"{API}/auth/login", json={"email": email, "password": "Second-Pass-2026"}).status_code == 200


def test_role_enforcement(admin):
    email = f"pytest-{RUN.lower()}@example.com"
    r = admin.post(f"{API}/admin/users", json={"email": email, "name": "Pytest User", "role": "cpse_user",
                                               "cpse_code": "IOCL", "password": "Pytest-Pass-2026"})
    assert r.status_code == 200, r.text
    user = TestClient(app)
    assert user.post(f"{API}/auth/login", json={"email": email, "password": "Pytest-Pass-2026"}).status_code == 200
    assert user.post(f"{API}/review/0/decision", json={"decision": "approve"}).status_code == 403
    assert user.post(f"{API}/ingest/upload", data={"cpse_code": "ONGC"},
                     files={"file": ("x.csv", HEADER.encode(), "text/csv")}).status_code == 403
    assert user.get(f"{API}/audit").status_code == 403
    assert user.put(f"{API}/admin/dictionary", json={"abbreviations": {"x": "y"}}).status_code == 403
    assert user.get(f"{API}/integrations/export/ONGC").status_code == 403
    assert user.get(f"{API}/integrations/export/IOCL").status_code == 200


def test_settings_are_validated(admin):
    bad = {"thresholds": {"review_floor": 0.9, "equivalent": 0.8, "near": 0.85, "auto_suggest": 0.95}}
    assert admin.put(f"{API}/admin/settings", json=bad).status_code == 422


# ---- pipeline, review, NMC ---------------------------------------------------------------------------------------

@needs_pipeline
def test_upload_report(ingested):
    assert ingested["IOCL"]["processed_rows"] == 3 and ingested["ONGC"]["processed_rows"] == 4
    assert ingested["IOCL"]["report"]["errors"] == []


@needs_pipeline
def test_same_bolt_written_differently_is_suggested(ingested):
    p = pair("IO1", "ON1")
    assert p is not None, "the two M12x50 bolts were never paired"
    assert p.status in ("suggested", "approved") and not p.gate_failures
    assert p.match_type in ("EXACT_DUPLICATE", "NEAR_DUPLICATE", "FUNCTIONAL_EQUIVALENT")


@needs_pipeline
def test_identical_gate_valves_are_exact_duplicates(ingested):
    p = pair("IO2", "ON3")
    assert p is not None and p.match_type == "EXACT_DUPLICATE"


@needs_pipeline
@pytest.mark.parametrize("a,b,key", [("IO1", "ON2", "thread"), ("IO2", "ON4", "rating")])
def test_hard_negatives_are_never_suggested(ingested, a, b, key):
    assert key in gate_failures(stored_attributes(a), stored_attributes(b))
    p = pair(a, b)
    assert p is None or (p.status == "blocked" and key in p.gate_failures)


@needs_pipeline
def test_blocked_pair_cannot_be_approved(ingested, admin):
    p = pair("IO2", "ON4")
    if p is None:
        pytest.skip("the 150#/300# pair was not retrieved as a candidate")
    r = admin.post(f"{API}/review/{p.id}/decision", json={"decision": "approve"})
    assert r.status_code == 409


@needs_pipeline
def test_approval_issues_a_valid_national_code(approved, admin):
    assert is_valid(approved)
    detail = admin.get(f"{API}/materials/{approved}").json()
    assert {code("IO1"), code("ON1")} <= {x["legacy_code"] for x in detail["legacy"]}
    assert detail["valid_check_digit"] and detail["active_nmc"] == approved and detail["status"] == "active"
    assert detail["standard_description"].startswith("BOLT")
    resolved = admin.get(f"{API}/legacy/ONGC/{code('ON1')}").json()
    assert resolved["active_nmc"] == approved


@needs_pipeline
def test_approval_is_audited(approved):
    with SessionLocal() as db:
        actions = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.entity_id == approved)}
        mapped = db.query(AuditLog).filter(AuditLog.action == "map", AuditLog.after["nmc"].astext == approved).count()
    assert "create" in actions and mapped >= 2


@needs_pipeline
def test_search_reads_the_query(ingested, admin):
    body = admin.get(f"{API}/search", params={"q": "hex bolt M12 x 50 SS 304"}).json()
    assert body["query"]["attributes"]["thread"] == "12" and body["query"]["attributes"]["grade"] == "SS304"
    hits = body["national"] + body["legacy"]
    best = min(hits, key=lambda h: (bool(h["gate_failures"]), -h["score"]))
    assert not best["gate_failures"] and best["score"] >= 0.7


@needs_pipeline
def test_export_analytics_graph_audit(approved, admin):
    r = admin.get(f"{API}/integrations/export/IOCL")
    assert r.status_code == 200 and r.content[:2] == b"PK"                       # an .xlsx is a zip
    csv_text = admin.get(f"{API}/integrations/export/IOCL", params={"format": "csv"}).content.decode("utf-8-sig")
    assert code("IO1") in csv_text and approved in csv_text
    k = admin.get(f"{API}/analytics/kpis").json()
    assert k["legacy_items"] >= 7 and k["national_codes"] >= 1 and k["mapped_items"] >= 2
    for path in ("by-cpse", "categories", "match-types", "aggregation", "activity"):
        assert admin.get(f"{API}/analytics/{path}").status_code == 200, path
    g = admin.get(f"{API}/graph/{approved}").json()
    assert {"nmc", "legacy", "cpse"} <= {n["type"] for n in g["nodes"]}
    trail = admin.get(f"{API}/audit", params={"entity": "national_material", "entity_id": approved}).json()
    assert trail["total"] >= 1
