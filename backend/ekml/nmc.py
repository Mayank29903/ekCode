def luhn_digit(payload: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(payload)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def make_nmc(category4: str, serial: int) -> str:
    """NMC-CCCC-SSSSSS-K: 4-digit category prefix, 6-digit serial, Luhn check digit over both."""
    if len(category4) != 4 or not category4.isdigit():
        raise ValueError(f"category prefix must be 4 digits, got {category4!r}")
    if not 0 < serial <= 999_999:
        raise ValueError(f"serial must be 1..999999, got {serial}")
    body = f"{category4}{serial:06d}"
    return f"NMC-{category4}-{serial:06d}-{luhn_digit(body)}"


def is_valid(nmc: str) -> bool:
    try:
        prefix, c, s, k = nmc.strip().upper().split("-")
        return (prefix == "NMC" and len(c) == 4 and len(s) == 6 and len(k) == 1
                and luhn_digit(c + s) == int(k))
    except ValueError:
        return False
