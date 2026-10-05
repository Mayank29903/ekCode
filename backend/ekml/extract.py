import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from .normalize import normalize, to_number


@lru_cache
def nouns() -> dict:
    return yaml.safe_load((Path(__file__).parent / "dictionaries" / "nouns.yaml").read_text(encoding="utf-8"))


# An "l" followed by a number is a length marker ("ss316 l50"), not the low-carbon grade suffix ("ss316l").
_L = r"(?:\s?l(?!\s*-?\s*\d))?"

# Length: "m12 x 50", "m12 x 1.75 x 50", "length 50", "l 50", "l-50"; an optional unit converts metres to mm.
_LENGTH = re.compile(r"(?:\bm\d{1,3}(?:\s*x\s*\d\.\d{1,2})?\s*x\s*|\blength\s*|\bl\s*-?\s*)"
                     r"(\d{1,5}(?:\.\d+)?)\s*(mm|metres?|meters?|m)?\b")

PATTERNS: dict[str, str] = {
    "thread": r"\bm(\d{1,3})\b",
    "length_mm": _LENGTH.pattern,
    "size_in": r"\b(\d+(?:\.\d+)?)\s*in\b",
    "size_mm": r"\b(\d{1,4}(?:\.\d+)?)\s*mm\b",
    "grade": (rf"\b(?:stainless steel\s*|ss\s*)(3\d{{2}}{_L})\b"
              rf"|\b(3\d{{2}}(?:\s?l)?)\s+stainless steel\b"
              rf"|\b(a\s?105|a\s?106\s?(?:gr\.?\s?)?b|a\s?182\s?(?:gr\.?\s?)?f\s?\d+{_L}|a\s?193\s?(?:gr\.?\s?)?b\s?7"
              rf"|is\s?2062|en\s?8|wcb"
              rf"|cf\s?8\s?m?)\b"),
    # ASME classes (150#, 300 lb, class 600, cl 150) and European PN ratings (pn 16) are kept apart on purpose:
    # PN16 is not the same rating as class 150, so the two never compare equal.
    "rating": r"\b(\d{3,4})\s?(?:#|lbs?\b|class\b)|\b(?:class|cl)\.?\s?(\d{3,4})\b|\b(pn\s?\d{1,3})\b",
    "schedule": r"\bschedule\s?(\d{2,3}|xs|xxs|std)\b",
    "standard": (r"\b((?:asme\s?)?b\s?16\.\d+|asme\s?b\s?\d+(?:\.\d+)?|api\s?(?:\d{1,2}\s?[a-z](?![a-z])|\d+)"
                 r"|is\s?\d{3,5}|din\s?\d+|astm\s?a\s?\d+|bs\s?\d{3,5}|en\s?\d{3,5})\b"),
    "bearing_no": r"\b(\d{4,5}(?:\s?-?\s?(?:zz|2\s?rs|2\s?z|rs|z|c\s?[34]))*)\b",
    "cores": r"\b(\d{1,2}(?:\.5)?)\s?c(?:ores?)?\b",
    "area_sqmm": r"\b(\d{1,3}(?:\.\d+)?)\s?(?:sq\.?\s?mm|mm\s?2)\b",
    "voltage": r"\b(\d{1,3}(?:\.\d+)?\s?kv)\b",
    "conductor": r"\b(copper|aluminium|aluminum)\b",
}
_COMPILED = {k: re.compile(p) for k, p in PATTERNS.items()}

# Keys that only mean something for one kind of item ("6205" is a bearing number only on a bearing).
ONLY_FOR = {"bearing_no": {"BEARING"}, "cores": {"CABLE"}, "area_sqmm": {"CABLE"}, "voltage": {"CABLE"},
            "conductor": {"CABLE"}}
FASTENERS = {"BOLT", "STUD BOLT", "NUT", "WASHER"}
BOLTS = {"BOLT", "STUD BOLT"}
NUMERIC_KEYS = {"thread", "length_mm", "size_in", "size_mm", "rating", "cores", "area_sqmm"}

# "Bolt hexagonal SS 12x50mm": diameter x length without the M prefix.
_DXL = re.compile(r"\b(\d{1,2})\s*x\s*(\d{2,4})\s*(?:mm)?\b")

# Nominal bore in mm (DN) -> nominal pipe size in inches (NPS).
DN_TO_NPS = {15: 0.5, 20: 0.75, 25: 1, 32: 1.25, 40: 1.5, 50: 2, 65: 2.5, 80: 3, 90: 3.5, 100: 4, 125: 5,
             150: 6, 200: 8, 250: 10, 300: 12, 350: 14, 400: 16, 450: 18, 500: 20, 600: 24, 700: 28,
             750: 30, 800: 32, 900: 36, 1000: 40, 1200: 48}
_NUM = r"\d+[\s-]\d+/\d+|\d+/\d+|\d+(?:\.\d+)?"
_NB = re.compile(rf"\b({_NUM})\s*(?:mm\s*)?(nominal bore|dn|nps)\b|\b(nominal bore|dn|nps)\s*({_NUM})\b")

# Text after these words describes what the item is used with, not what it is ("bolt for flange").
_CONNECTOR = re.compile(r"\b(?:for|with|suitable|to suit|used in|used for|compatible)\b")


@lru_cache
def _noun_patterns() -> list[tuple[bool, int, re.Pattern, str]]:
    """(weak, keyword length, compiled keyword, noun), compiled once: detect_noun runs for every row."""
    return [(bool(spec.get("weak")), len(kw), re.compile(rf"\b{re.escape(kw)}\b"), noun)
            for noun, spec in nouns().items() for kw in spec["keywords"]]


def detect_noun(norm: str) -> str | None:
    """Strong nouns beat weak ones, then the longest keyword wins, then the earliest one."""
    head = _CONNECTOR.split(norm, maxsplit=1)[0].strip() or norm
    hits = [(weak, -n, m.start(), noun) for weak, n, pat, noun in _noun_patterns() if (m := pat.search(head))]
    return min(hits)[3] if hits else None


def nominal_size(norm: str) -> float | None:
    """'50 nominal bore' / 'dn 50' -> 2.0 ; '1/2 nominal bore' / 'nps 2' -> inches as written."""
    m = _NB.search(norm)
    if not m:
        return None
    num, kind = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
    val = to_number(num)
    if kind == "nps" or "/" in num:
        return val
    if val in DN_TO_NPS:
        return float(DN_TO_NPS[val])
    return val if val <= 12 else None          # "2 NB" is written in inches


def _length(norm: str) -> str | None:
    """Length in mm: 'l 6 m' -> '6000', 'm12 x 50' -> '50'. Decimal, not float: 1.005 m must be 1005, not 1004.99…"""
    m = _LENGTH.search(norm)
    if not m:
        return None
    value = Decimal(m.group(1))
    return str(value * 1000 if m.group(2) and m.group(2) != "mm" else value)


def clean_value(key: str, v: str) -> str:
    """Canonical form of an attribute value, so equal things compare equal in gates and features."""
    v = re.sub(r"\s+", "", v).upper()
    if key == "grade":
        v = re.sub(r"GR\.?|[.-]", "", v)       # A106 GR.B == A106B
    elif key == "bearing_no":
        v = v.replace("-", "")                 # 6205-2RS == 6205 2RS
    elif key == "standard":
        v = re.sub(r"^ASME(?=B\d)", "", v)     # ASME B16.20 == B16.20
    elif key == "conductor":
        v = v.replace("ALUMINUM", "ALUMINIUM")
    if re.fullmatch(r"\d+(?:\.\d+)?", v):
        v = format(Decimal(v).normalize(), "f")  # 50.0 == 50, 0.50 == 0.5, 6000.0 == 6000
    return v


def _set(attrs: dict, conf: dict, key: str, val: str, c: float) -> None:
    attrs[key], conf[key] = clean_value(key, val), c


def _drop(attrs: dict, conf: dict, key: str) -> None:
    attrs.pop(key, None)
    conf.pop(key, None)


def extract(norm: str) -> tuple[dict, dict]:
    attrs: dict[str, str] = {}
    conf: dict[str, float] = {}
    noun = detect_noun(norm)
    if noun:
        attrs["noun"], conf["noun"] = noun, 0.9
    for key, pat in _COMPILED.items():
        if key in ONLY_FOR and noun not in ONLY_FOR[key]:
            continue
        if key == "thread" and noun and noun not in FASTENERS:
            continue
        if key == "length_mm":
            if (val := _length(norm)) is not None:
                _set(attrs, conf, key, val, 0.95)
            continue
        m = pat.search(norm)
        if m and (val := next((g for g in m.groups() if g), None)):
            _set(attrs, conf, key, val, 0.95)
    if noun in BOLTS and "thread" not in attrs and (m := _DXL.search(norm)):
        _set(attrs, conf, "thread", m.group(1), 0.8)
        if "length_mm" not in attrs:
            _set(attrs, conf, "length_mm", m.group(2), 0.8)
    if "size_in" not in attrs and (nps := nominal_size(norm)) is not None:
        _set(attrs, conf, "size_in", f"{nps:g}", 0.8)
        _drop(attrs, conf, "size_mm")          # the mm figure was the nominal bore
    if "thread" in attrs or "area_sqmm" in attrs:
        _drop(attrs, conf, "size_mm")          # a bolt's length / a cable's mm² is not a size
    if "size_mm" in attrs and attrs["size_mm"] == attrs.get("length_mm"):
        _drop(attrs, conf, "size_mm")          # "L 6000MM": the mm figure is the length
    if attrs.get("grade", "").startswith("3"):
        attrs["grade"] = "SS" + attrs["grade"]
    return attrs, conf


# ---- values typed by a person or returned by an LLM -------------------------------------------------------------
# Tolerates the usual decorations around a number: M12, 50MM, 2", 150#, 300 LB, CLASS 600, 95 SQMM.
_NUMBER = re.compile(r"(?:M|CLASS\s*)?(\d+(?:\.\d+)?)\s*(?:MM|IN|INCH|\"|#|LBS?|C|CORE|SQ\.?\s?MM)?")
_TEXT = re.compile(r"[A-Z0-9][A-Z0-9 .#/-]{0,39}")
# Some patterns only fire next to a word that gives them meaning.
_CONTEXT = {"schedule": "schedule ", "bearing_no": "bearing ", "voltage": "cable ", "conductor": "cable "}


def canonical_value(key: str, value: object) -> str | None:
    """The value in exactly the form the regex path produces, or None if it cannot be parsed.
    A differently spelled value ("316" vs "SS316") would otherwise trip a hard gate."""
    v = str(value).strip().upper()
    if not v:
        return None
    if key == "noun":
        return v if v in nouns() else None
    if key == "rating" and re.fullmatch(r"PN\s?\d{1,3}", v):
        return clean_value(key, v)
    if key in NUMERIC_KEYS:
        m = _NUMBER.fullmatch(v)
        return clean_value(key, m.group(1)) if m else None
    if key == "grade" and re.fullmatch(r"3\d{2}L?", v):
        return "SS" + v
    if key in PATTERNS:
        attrs, _ = extract(normalize(_CONTEXT.get(key, "") + v))
        return attrs.get(key)
    return clean_value(key, v) if _TEXT.fullmatch(v) else None
