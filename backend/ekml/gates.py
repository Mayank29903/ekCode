# Any mismatch on these keys means DIFFERENT material, regardless of similarity.
# A key present on only one side is not a conflict: it lowers the attribute feature instead.
HARD_KEYS = ["noun", "thread", "length_mm", "size_in", "size_mm", "rating", "schedule", "grade",
             "bearing_no", "cores", "area_sqmm", "voltage", "conductor"]


def gate_failures(a: dict, b: dict) -> list[str]:
    return [k for k in HARD_KEYS if k in a and k in b and str(a[k]) != str(b[k])]
