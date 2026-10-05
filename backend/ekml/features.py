from rapidfuzz import fuzz

SPEC_KEYS = ["standard", "grade", "rating"]


def attribute_score(a: dict, b: dict) -> float:
    """1 per agreeing attribute, 0 per conflict, 0.5 per attribute stated on one side only.
    One-sided values count as uncertain, so "BOLT M12" vs "BOLT M12 X 50 SS304" is not a perfect match."""
    keys = (set(a) | set(b)) - {"noun"}
    if not keys:
        return 0.5
    total = sum((1.0 if str(a[k]) == str(b[k]) else 0.0) if k in a and k in b else 0.5 for k in keys)
    return total / len(keys)


def spec_score(a: dict, b: dict) -> float:
    vals = []
    for k in SPEC_KEYS:
        if k in a and k in b:
            vals.append(1.0 if a[k] == b[k] else 0.0)
        elif k in a or k in b:
            vals.append(0.5)
    return sum(vals) / len(vals) if vals else 0.5


def _same(x: str | None, y: str | None) -> float:
    """1 if both known and equal, 0 if both known and different, 0.5 if either is unknown."""
    return 0.5 if not (x and y) else 1.0 if x == y else 0.0


def pair_features(sim: float, na: str, nb: str, aa: dict, ab: dict, ua: str | None, ub: str | None) -> dict:
    return {
        "semantic": round(float(sim), 4),
        "lexical": round(fuzz.token_set_ratio(na, nb) / 100, 4),
        "attribute": round(attribute_score(aa, ab), 4),
        "spec": round(spec_score(aa, ab), 4),
        "unit": _same(ua, ub),
        "category": _same(aa.get("noun"), ab.get("noun")),
        # Not a model feature (see FEATURE_KEYS). token_set_ratio scores a subset as 1.0
        # ("bolt m12" vs "bolt m12 zinc plated"), so exact-duplicate detection uses the stricter sort ratio.
        "text_exact": round(fuzz.token_sort_ratio(na, nb) / 100, 4),
    }
