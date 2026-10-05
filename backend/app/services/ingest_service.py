import codecs
import hashlib
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz
from sqlalchemy import case, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ekml.embed import embed
from ekml.extract import extract
from ekml.llm import fill_gaps, needs_llm
from ekml.normalize import normalize, normalize_uom

from ..models import IngestJob, RawMaterial
from ..settings_store import flags

SAP_FIELDS = {
    "MATNR": ["matnr", "material", "material code", "material no", "material number", "item code", "code",
              "sap code", "legacy code", "mat code"],
    "MAKTX": ["maktx", "description", "material description", "short text", "item description", "desc",
              "material desc", "item name"],
    "LONG_TEXT": ["long text", "long description", "po text", "specification", "spec"],
    "MEINS": ["meins", "uom", "unit", "base unit", "unit of measure", "base unit of measure"],
    "MATKL": ["matkl", "material group", "group", "category"],
    "PRICE": ["price", "unit price", "rate", "netpr", "last price"],
    "QTY": ["annual qty", "quantity", "annual quantity", "consumption", "qty", "annual consumption"],
}
REQUIRED = ("MATNR", "MAKTX")
UPSERT_BATCH = 1000
_DELIMITERS = (",", ";", "\t", "|")


def _decode_sample(raw: bytes) -> tuple[str, str]:
    """UTF-8 (with or without BOM) when valid, else Windows-1252, the usual encoding of Excel 'Save as CSV'."""
    try:
        return "utf-8-sig", codecs.getincrementaldecoder("utf-8-sig")().decode(raw, final=False)
    except UnicodeDecodeError:
        return "cp1252", raw.decode("cp1252", errors="replace")


def _delimiter(sample: str) -> str:
    header = sample.splitlines()[0] if sample else ""
    counts = {d: header.count(d) for d in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def read_table(path: Path, nrows: int | None = None) -> pd.DataFrame:
    """Every cell as text. "NA", "N/A" or "NULL" stay literal (they can be real codes or descriptions).
    A CSV row that cannot be split into the header's columns (a stray delimiter inside a description) is skipped
    and listed in df.attrs["bad_lines"], instead of failing the whole upload."""
    bad: list[str] = []
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str, nrows=nrows, keep_default_na=False)
    else:
        with path.open("rb") as fh:
            enc, sample = _decode_sample(fh.read(65536))
        sep = _delimiter(sample)
        opts = dict(dtype=str, nrows=nrows, sep=sep, encoding=enc, encoding_errors="replace", keep_default_na=False)
        try:
            df = pd.read_csv(path, **opts)
        except pd.errors.ParserError:
            def skip(fields: list[str]):
                bad.append(sep.join(fields)[:200])
                return None
            df = pd.read_csv(path, engine="python", on_bad_lines=skip, **opts)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("")
    df.attrs["bad_lines"] = bad
    return df


def auto_map(columns: list[str]) -> dict:
    """Best fuzzy match per SAP field; each column is used at most once, strongest matches first."""
    keys = {c.lower().strip().replace("_", " "): c for c in columns}
    cands = []
    for field, syns in SAP_FIELDS.items():
        for key, col in keys.items():
            score = max(fuzz.ratio(s, key) for s in syns)
            if score >= 80:
                cands.append((score, field, col))
    out, used = {}, set()
    for _, field, col in sorted(cands, key=lambda c: -c[0]):
        if field not in out and col not in used:
            out[field] = col
            used.add(col)
    return out


def _num(v) -> float | None:
    s = re.sub(r"[^\d.\-]", "", str(v))         # "₹ 1,250.00" -> "1250.00"
    try:
        x = float(s) if s else None
    except ValueError:
        return None
    return x if x is not None and abs(x) < 1e12 else None   # Numeric(14, 2)


def _stage(db: Session, job: IngestJob, stage: str, progress: float):
    job.stage, job.progress = stage, round(min(max(progress, 0.0), 1.0), 3)
    db.commit()


def _upsert(batch: list[dict]):
    """Idempotent re-upload (ADR-16). Rows whose text is unchanged keep their status, so they are not
    re-embedded or re-matched; price, quantity and group are always refreshed."""
    stmt = insert(RawMaterial).values(batch)
    ex = stmt.excluded
    return stmt.on_conflict_do_update(
        index_elements=["cpse_id", "legacy_code"],
        set_={"description": ex.description, "long_text": ex.long_text, "uom_raw": ex.uom_raw,
              "material_group": ex.material_group, "unit_price": ex.unit_price, "annual_qty": ex.annual_qty,
              "source": ex.source, "job_id": ex.job_id, "row_hash": ex.row_hash,
              "status": case((RawMaterial.row_hash.is_distinct_from(ex.row_hash), "ingested"),   # NULL-safe
                             else_=RawMaterial.status)},
    ).returning(RawMaterial.id, RawMaterial.status)


def parse_rows(df: pd.DataFrame, m: dict, job: IngestJob) -> tuple[list[dict], list[dict], list[dict]]:
    def col(row, field):
        c = m.get(field)
        return str(row.get(c, "")).strip() if c else ""

    rows: dict[str, dict] = {}
    errors = [{"row": None, "error": f"could not be split into columns: {line}"}
              for line in df.attrs.get("bad_lines", [])]
    warnings = []
    for i, row in enumerate(df.to_dict("records")):
        line = i + 2                                   # 1-based, after the header row
        code, desc = col(row, "MATNR"), col(row, "MAKTX")
        if not code or not desc:
            errors.append({"row": line, "error": "missing material code or description"})
            continue
        if len(code) > 60:
            errors.append({"row": line, "error": "material code is longer than 60 characters"})
            continue
        if code in rows:
            warnings.append({"row": line, "warning": f"code {code} appears more than once; the last row wins"})
        long_text = col(row, "LONG_TEXT") or None
        uom = col(row, "MEINS")[:20] or None
        rows[code] = dict(cpse_id=job.cpse_id, legacy_code=code, description=desc, long_text=long_text,
                          uom_raw=uom, material_group=col(row, "MATKL")[:40] or None,
                          unit_price=_num(col(row, "PRICE")), annual_qty=_num(col(row, "QTY")),
                          source=job.source, job_id=job.id, status="ingested",
                          row_hash=hashlib.sha256(f"{code}|{desc}|{long_text or ''}|{uom or ''}".encode()).hexdigest())
    return list(rows.values()), errors, warnings


def run_pipeline(db: Session, job: IngestJob) -> list[int]:
    from .match_service import match_materials
    df = read_table(Path(job.path)) if job.path else pd.DataFrame()
    job.status, job.total_rows, job.processed_rows = "running", len(df), 0
    _stage(db, job, "parsing", 0)
    values, errors, warnings = parse_rows(df, job.column_map or {}, job)

    ids, unchanged = [], 0                             # ids = new or changed rows that need processing
    for start in range(0, len(values), UPSERT_BATCH):
        for rid, status in db.execute(_upsert(values[start:start + UPSERT_BATCH])).all():
            if status in ("ingested", "embedded"):
                ids.append(rid)
            else:
                unchanged += 1
        job.processed_rows = min(start + UPSERT_BATCH, len(values))
        _stage(db, job, "parsing", job.processed_rows / max(len(values), 1))
    job.error_rows = len(errors)
    job.report = {"errors": errors[:500], "warnings": warnings[:500], "valid_rows": len(values),
                  "new_or_changed": len(ids), "unchanged": unchanged}
    db.commit()

    process_ids(db, job, ids)
    match_materials(db, ids, on_progress=lambda p: _stage(db, job, "matching", p))
    # A changed row that was already mapped goes back through matching; keep its status truthful.
    db.execute(text("UPDATE raw_material r SET status = 'mapped' FROM code_mapping m "
                    "WHERE m.raw_material_id = r.id AND r.status <> 'mapped'"))
    job.status, job.processed_rows = "done", len(values)
    _stage(db, job, "done", 1)
    return ids


def _release(db: Session, objs) -> None:
    """Drop processed rows from the identity map, so a 50k-row job does not keep every embedding in memory."""
    for o in objs:
        db.expunge(o)


def process_ids(db: Session, job: IngestJob | None, ids: list[int], batch: int = 256):
    use_llm = flags(db)["use_llm"]
    total = max(len(ids), 1)
    if job:
        _stage(db, job, "normalizing", 0)
    for start in range(0, len(ids), batch):            # pass 1: normalize + extract attributes
        chunk = db.query(RawMaterial).filter(RawMaterial.id.in_(ids[start:start + batch])).all()
        for r in chunk:
            r.norm_text = normalize(f"{r.description} {r.long_text or ''}")
            attrs, conf = extract(r.norm_text)
            if use_llm and needs_llm(attrs):          # only rows the rules could not read well
                attrs, conf = fill_gaps(attrs, conf, r.description)
            r.attributes, r.attr_confidence = attrs, conf
            r.uom_code = normalize_uom(r.uom_raw)
        db.commit()
        if job:
            _stage(db, job, "normalizing", (start + batch) / total)
        _release(db, chunk)
    if job:
        _stage(db, job, "embedding", 0)                # the first call may download the model
    for start in range(0, len(ids), batch):            # pass 2: embeddings
        chunk = db.query(RawMaterial).filter(RawMaterial.id.in_(ids[start:start + batch])).all()
        vecs = embed([r.norm_text or r.description.lower() for r in chunk])
        for r, v in zip(chunk, vecs):
            r.embedding, r.status = v.tolist(), "embedded"
        db.commit()
        if job:
            _stage(db, job, "embedding", (start + batch) / total)
        _release(db, chunk)
