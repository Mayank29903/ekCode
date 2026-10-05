"""UNSPSC suggestion. Requires data/reference/unspsc.csv (code,title) produced by scripts/import_unspsc_pdf.py.
Without the file every material falls back to category 9999 (Unclassified) — the app still works.

The index is keyed by the file's modification time, so importing a new code list takes effect without a
restart, and the embedding cache is keyed by the embedding model, so changing EMBED_MODEL can never mix
vectors of different sizes."""
import csv
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from .embed import embed, model_name

log = logging.getLogger(__name__)
REF = Path(os.getenv("DATA_DIR", "/data")) / "reference" / "unspsc.csv"


def cache_path(ref: Path = REF) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model_name()).strip("-").lower()
    return ref.with_name(f"{ref.stem}.{slug}.npy")


@lru_cache(maxsize=2)
def _load(path: str, mtime: float):
    ref = Path(path)
    try:
        with ref.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if (r.get("code") or "").isdigit() and len(r["code"]) == 8 and not r["code"].endswith("00")
                    and (r.get("title") or "").strip()]
    except (OSError, csv.Error, UnicodeDecodeError) as e:
        log.warning("cannot read %s: %s", ref, e)
        return None, None
    if not rows:
        return None, None
    cache = cache_path(ref)
    vecs = None
    if cache.exists() and cache.stat().st_mtime >= mtime:
        try:
            vecs = np.load(cache)
        except (OSError, ValueError):
            vecs = None
    if vecs is None or len(vecs) != len(rows):          # missing or stale cache
        vecs = np.asarray(embed([r["title"] for r in rows]), dtype=np.float32)
        try:
            np.save(cache, vecs)
        except OSError as e:
            log.warning("cannot write %s: %s", cache, e)
    return rows, vecs


def _index():
    try:
        mtime = REF.stat().st_mtime
    except OSError:
        return None, None
    return _load(str(REF), mtime)


def warm() -> int:
    """(Re)build the index and its embedding cache now; returns the number of commodity codes."""
    _load.cache_clear()
    rows, _ = _index()
    return len(rows or [])


def suggest(text: str, k: int = 3, vec: np.ndarray | None = None) -> list[dict]:
    """Pass `vec` (the material's own embedding) to skip re-embedding during bulk ingest."""
    rows, vecs = _index()
    if rows is None:
        return []
    q = np.asarray(vec if vec is not None else embed([text])[0], dtype=np.float32)
    if q.shape[-1] != vecs.shape[1]:
        log.warning("embedding size %s does not match the UNSPSC index (%s)", q.shape[-1], vecs.shape[1])
        return []
    sims = vecs @ q
    top = np.argsort(-sims)[:k]
    return [{"code": rows[i]["code"], "title": rows[i]["title"], "score": round(float(sims[i]), 3)} for i in top]


def category4(text: str, vec: np.ndarray | None = None) -> tuple[str, str | None]:
    s = suggest(text, 1, vec)
    return (s[0]["code"][:4], s[0]["code"]) if s else ("9999", None)
