from collections import Counter

import numpy as np
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from ekml import taxonomy
from ekml.nmc import make_nmc
from ekml.standardize import standard_description

from ..models import NationalMaterial, RawMaterial

_SEQUENCES: set[str] = set()


def canonical_attributes(members: list[RawMaterial]) -> dict:
    """Most common value per attribute across the members (ties: the first member's value)."""
    out = {}
    keys = {k for m in members for k in (m.attributes or {})}
    for k in sorted(keys):
        vals = [m.attributes[k] for m in members if m.attributes and k in m.attributes]
        out[k] = Counter(vals).most_common(1)[0][0]
    return out


def _category(members: list[RawMaterial], attrs: dict) -> tuple[str, str | None]:
    first = members[0]
    # Reuse the stored vector instead of embedding again (keeps the model out of the API process).
    vec = np.asarray(first.embedding, dtype=np.float32) if first.embedding is not None else None
    cat4, unspsc = taxonomy.category4(f"{attrs.get('noun', '')} {first.norm_text or first.description}", vec)
    if len(cat4) != 4 or not cat4.isdigit():   # cat4 becomes part of a SQL identifier below
        return "9999", None
    return cat4, unspsc


def _ensure_sequence(db: Session, seq: str) -> None:
    """Create the category's serial sequence once, outside the caller's transaction (no DDL lock held while an
    approval is open). Two first approvals in one category at the same moment are harmless."""
    if seq in _SEQUENCES:
        return
    with db.get_bind().connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {seq} MAXVALUE 999999"))
        except (IntegrityError, ProgrammingError):
            pass                                    # created concurrently by another request
    _SEQUENCES.add(seq)


def issue_nmc(db: Session, members: list[RawMaterial]) -> NationalMaterial:
    attrs = canonical_attributes(members)
    cat4, unspsc = _category(members, attrs)
    seq = f"nmc_seq_{cat4}"                      # digits only (checked above) -> safe identifier
    _ensure_sequence(db, seq)
    serial = db.execute(text(f"SELECT nextval('{seq}')")).scalar_one()
    uoms = [m.uom_code for m in members if m.uom_code]
    nm = NationalMaterial(nmc=make_nmc(cat4, serial), noun=attrs.get("noun"),
                          standard_description=standard_description(attrs, members[0].description),
                          attributes=attrs, unspsc=unspsc,
                          uom_code=Counter(uoms).most_common(1)[0][0] if uoms else None)
    db.add(nm)
    db.flush()
    return nm
