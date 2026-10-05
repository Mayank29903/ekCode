from dataclasses import dataclass, field

from . import FEATURE_KEYS

WEIGHTS = {"semantic": 0.35, "lexical": 0.15, "attribute": 0.25, "spec": 0.10, "unit": 0.05, "category": 0.10}


@dataclass
class Decision:
    score: float
    match_type: str
    gates: list[str] = field(default_factory=list)


def weighted(f: dict) -> float:
    return sum(WEIGHTS[k] * f[k] for k in WEIGHTS)


def is_exact(f: dict) -> bool:
    """Same words (any order), every attribute stated on both sides and equal, units not in conflict.
    Kept strict because exact duplicates are the only pairs that may be auto-approved (ADR-19)."""
    return f.get("text_exact", f["lexical"]) >= 0.99 and f["attribute"] >= 0.99 and f["unit"] > 0


def decide(f: dict, gates: list[str], th: dict, model=None) -> Decision:
    s = float(model.predict_proba([[f[k] for k in FEATURE_KEYS]])[0][1]) if model is not None else weighted(f)
    if gates:
        return Decision(round(min(s, 0.49), 4), "DIFFERENT", gates)
    if is_exact(f):
        t = "EXACT_DUPLICATE"
    elif s >= th["near"]:
        t = "NEAR_DUPLICATE"
    elif s >= th["equivalent"] and f["spec"] >= 0.5:   # 0.5 = specs unstated, not in conflict (PRD §7.1)
        t = "FUNCTIONAL_EQUIVALENT"
    else:
        t = "DIFFERENT"
    return Decision(round(s, 4), t, [])
