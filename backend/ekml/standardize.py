from .extract import nouns

KEY_TITLES = {"thread": "THREAD", "length_mm": "LENGTH", "size_in": "SIZE", "size_mm": "SIZE", "grade": "MATERIAL",
              "rating": "RATING", "schedule": "SCHEDULE", "standard": "STANDARD", "bearing_no": "BEARING NO",
              "cores": "CORES", "area_sqmm": "AREA", "voltage": "VOLTAGE", "conductor": "CONDUCTOR",
              "coating": "COATING"}
UNITS = {"length_mm": " MM", "size_in": " IN", "size_mm": " MM", "rating": "#", "area_sqmm": " SQ MM"}


def noun_phrase(noun: str) -> str:
    """Noun-modifier order: the class noun first, then its modifier. GATE VALVE -> VALVE, GATE."""
    *modifier, head = noun.split()
    return f"{head}, {' '.join(modifier)}" if modifier else head


def standard_description(attrs: dict, fallback: str = "") -> str:
    """e.g. BOLT; THREAD: M12; LENGTH: 50 MM; MATERIAL: SS304"""
    noun = attrs.get("noun")
    if not noun:
        return fallback.upper()[:120]
    order = nouns().get(noun, {}).get("order", [])
    parts = [noun_phrase(noun)]
    for k in order + [k for k in attrs if k not in order and k != "noun"]:
        if k in attrs and k in KEY_TITLES:
            v = f"M{attrs[k]}" if k == "thread" else f"{attrs[k]}{UNITS.get(k, '')}"
            parts.append(f"{KEY_TITLES[k]}: {v}")
    return "; ".join(dict.fromkeys(parts))
