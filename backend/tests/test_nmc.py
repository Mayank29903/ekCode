import re

import pytest

from ekml.nmc import is_valid, luhn_digit, make_nmc


def rebuild(body: str) -> str:
    """Put a 10-digit body back into NMC form, keeping the original check digit."""
    return f"NMC-{body[:4]}-{body[4:]}-{luhn_digit('3116000123')}"


def test_luhn_reference_value():
    assert luhn_digit("7992739871") == 3            # the textbook example: 79927398713 is valid


def test_format_and_validity():
    code = make_nmc("3116", 123)
    assert re.fullmatch(r"NMC-3116-000123-\d", code)
    assert is_valid(code)
    assert is_valid(code.lower())


def test_every_single_digit_typo_is_caught():
    body = "3116000123"
    for i, original in enumerate(body):
        for d in "0123456789":
            if d != original:
                assert not is_valid(rebuild(body[:i] + d + body[i + 1:])), (i, d)


def test_adjacent_transpositions_are_caught():
    body = "3116000123"
    for i in range(len(body) - 1):
        a, b = body[i], body[i + 1]
        if a == b or {a, b} == {"0", "9"}:        # Luhn's one blind spot: 09 <-> 90
            continue
        assert not is_valid(rebuild(body[:i] + b + a + body[i + 2:])), i


@pytest.mark.parametrize("category,serial", [("31A6", 1), ("311", 1), ("3116", 0), ("3116", 1_000_000)])
def test_invalid_inputs_are_refused(category, serial):
    with pytest.raises(ValueError):
        make_nmc(category, serial)


@pytest.mark.parametrize("code", ["", "NMC-3116-000123", "XYZ-3116-000123-1", "NMC-3116-000123-X",
                                  "NMC-ABCD-000123-1", "NMC-3116-123-1", "NMC-3116-000123-12"])
def test_malformed_codes_are_invalid(code):
    assert not is_valid(code)


def test_codes_differ_by_serial():
    assert make_nmc("9999", 1) != make_nmc("9999", 2)
