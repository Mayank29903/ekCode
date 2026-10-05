from sqlalchemy.orm import Session

from .models import Setting

# Seeded by init_db and used as fallbacks, so a missing or partial setting row can never break matching.
DEFAULTS = {
    "thresholds": {"near": 0.88, "equivalent": 0.78, "auto_suggest": 0.93, "review_floor": 0.70},
    "flags": {"auto_approve_exact": False, "use_llm": False},
}


def get_setting(db: Session, key: str) -> dict:
    s = db.get(Setting, key)
    return dict(s.value) if s and isinstance(s.value, dict) else {}


def put_setting(db: Session, key: str, value: dict) -> None:
    s = db.get(Setting, key)
    if s:
        s.value = value          # assign a new dict: in-place JSONB mutation is not tracked
    else:
        db.add(Setting(key=key, value=value))


def thresholds(db: Session) -> dict:
    return {**DEFAULTS["thresholds"], **get_setting(db, "thresholds")}


def flags(db: Session) -> dict:
    return {**DEFAULTS["flags"], **get_setting(db, "flags")}
