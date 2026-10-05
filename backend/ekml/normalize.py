import re
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import yaml

D = Path(__file__).parent / "dictionaries"
_OVERRIDE: dict[str, str] = {}


def _load(name: str) -> dict[str, str]:
    data = yaml.safe_load((D / name).read_text(encoding="utf-8")) or {}
    return {str(k).lower(): str(v) for k, v in data.items()}


@lru_cache
def _seed_abbr() -> dict[str, str]:
    return {k: v.lower() for k, v in _load("abbreviations.yaml").items()}


@lru_cache
def units() -> dict[str, str]:
    return _load("units.yaml")


def set_abbreviations(d: dict[str, str] | None) -> None:
    """Install the steward's dictionary; an empty one means "use the shipped YAML".
    Swapped in a single assignment, so a request running at that moment sees the old or the new dictionary,
    never a half-built one."""
    global _OVERRIDE
    _OVERRIDE = {str(k).strip().lower(): str(v).strip().lower() for k, v in (d or {}).items()}


def abbreviations() -> dict[str, str]:
    return _OVERRIDE or _seed_abbr()


def seed_abbreviations() -> dict[str, str]:
    """The shipped YAML dictionary (what Settings → Dictionary resets to)."""
    return dict(_seed_abbr())


# 1/2"  1-1/2"  1 1/2 in  2.5 inch. The look-behind stops "CL150 1/2 IN" being read as 150.5 inches:
# a mixed number's whole part (1-2 digits) must not continue a longer number.
INCH = re.compile(r"(?<![\d.])(\d{1,2}[\s-]\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2}|\d+(?:\.\d+)?)"
                  r"""\s*(?:"|''|in\b|inch(?:es)?\b)""", re.I)


def to_number(raw: str) -> float:
    """'1-1/2' -> 1.5, '3/4' -> 0.75, '2.5' -> 2.5"""
    parts = re.split(r"[\s-]+", raw.strip()) if "/" in raw else [raw.strip()]
    return float(sum(Fraction(p) for p in parts))


def _inch(m: re.Match) -> str:
    return f" {to_number(m.group(1)):g} in "


def normalize(text: str) -> str:
    if not text:
        return ""
    t = text.lower().replace("×", "x")
    t = re.sub(r"\b([a-z])\.([a-z])\.?(?=[\s\d]|$)", r"\1\2 ", t)  # s.s. / m.s / c.s.304 -> ss / ms / cs 304
    t = INCH.sub(_inch, t)
    t = re.sub(r"(?<=\d)\s*[x*]\s*(?=\d)", " x ", t)          # 12x50 -> 12 x 50
    t = re.sub(r"(?<=[a-z])-(?=\d)|(?<=\d)-(?=[a-z])", " ", t)  # sch-40 -> sch 40
    t = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", t)   # m12 -> m 12 ; 50mm -> 50 mm
    t = re.sub(r"\bm (\d)", r"m\1", t)                          # keep thread as m12
    t = re.sub(r"[^\w\s./#-]", " ", t)
    abbr = abbreviations()
    toks = []
    for tok in t.split():
        tok = tok.rstrip(".") or tok                            # "no." / "hex." -> "no" / "hex"
        toks.append(abbr.get(tok, tok))
    return re.sub(r"\s+", " ", " ".join(toks)).strip()


def normalize_uom(raw: str | None) -> str | None:
    if not raw:
        return None
    return units().get(raw.strip().lower().rstrip("."), raw.strip().upper())
