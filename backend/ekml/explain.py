LABELS = {"thread": "Thread", "length_mm": "Length (mm)", "size_in": "Size (in)", "size_mm": "Size (mm)",
          "grade": "Grade", "rating": "Rating", "schedule": "Schedule", "standard": "Standard",
          "noun": "Material type", "bearing_no": "Bearing no.", "cores": "Cores", "area_sqmm": "Area (sq mm)",
          "voltage": "Voltage", "conductor": "Conductor", "coating": "Coating"}


def explain(f: dict, a: dict, b: dict, gates: list[str]) -> list[dict]:
    """Chip data for the UI: match / diff / conflict / missing per attribute, plus the two similarity signals."""
    out = []
    for k in sorted(set(a) | set(b)):
        if k in a and k in b:
            kind = "conflict" if k in gates else ("match" if a[k] == b[k] else "diff")
            out.append({"kind": kind, "key": k, "label": LABELS.get(k, k), "a": a[k], "b": b[k]})
        else:
            out.append({"kind": "missing", "key": k, "label": LABELS.get(k, k), "a": a.get(k), "b": b.get(k)})
    out.append({"kind": "signal", "label": "Meaning similarity", "value": f["semantic"]})
    out.append({"kind": "signal", "label": "Text similarity", "value": f["lexical"]})
    return out
