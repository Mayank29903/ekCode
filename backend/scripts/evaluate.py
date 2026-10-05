"""Score EkCode's matcher against the seeded ground truth (PRD G1 and G2).

    python scripts/evaluate.py            # prints the report and writes $DATA_DIR/seed/eval_report.json
    python scripts/evaluate.py --strict   # exit 1 if a target is missed (for CI)

A pair is predicted "same material" when it was not blocked by a hard gate and its score is at or above the
threshold. Steward decisions do not change the prediction: a suggestion that was later rejected still counts
as a prediction the model made. Targets: F1 >= 0.90 at the review floor (G1); precision >= 0.97 at the
auto threshold and 100% of retrieved hard negatives blocked (G2).
"""
import argparse
import csv
import itertools
import json
import os
import sys
from pathlib import Path

from app.db import SessionLocal
from app.models import Cpse, MatchPair, RawMaterial
from app.settings_store import thresholds

F1_TARGET, PRECISION_TARGET = 0.90, 0.97


def prf(pred: set, truth: set) -> dict:
    tp = len(pred & truth)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(truth) if truth else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"predicted": len(pred), "true_positives": tp, "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(f1, 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(Path(os.getenv("DATA_DIR", "/data")) / "seed"))
    ap.add_argument("--strict", action="store_true", help="exit with status 1 when a target is missed")
    args = ap.parse_args()
    folder = Path(args.dir)
    if not (folder / "truth.csv").exists():
        sys.exit(f"No truth.csv in {folder}. Run generate_cpse_seed.py and load_seed.py first.")

    with (folder / "truth.csv").open(encoding="utf-8", newline="") as fh:
        truth = {(r["cpse"], r["legacy_code"]): r["item_id"] for r in csv.DictReader(fh)}
    negatives: dict[frozenset, str] = {}
    if (folder / "hard_negatives.csv").exists():
        with (folder / "hard_negatives.csv").open(encoding="utf-8", newline="") as fh:
            negatives = {frozenset((r["item_a"], r["item_b"])): r["key"] for r in csv.DictReader(fh)}

    with SessionLocal() as db:
        th = thresholds(db)
        rows = (db.query(RawMaterial.id, Cpse.code, RawMaterial.legacy_code, RawMaterial.description)
                .join(Cpse, Cpse.id == RawMaterial.cpse_id).filter(RawMaterial.source == "synthetic").all())
        item_of = {rid: truth[(code, legacy)] for rid, code, legacy, _ in rows if (code, legacy) in truth}
        desc = {rid: f"{code} {legacy}: {d}" for rid, code, legacy, d in rows}
        pairs = [(a, b, score, status, mtype) for a, b, score, status, mtype in
                 db.query(MatchPair.a_id, MatchPair.b_id, MatchPair.score, MatchPair.status, MatchPair.match_type)
                 if a in item_of and b in item_of]
    if not item_of:
        sys.exit("No synthetic rows in the database match truth.csv. Run scripts/load_seed.py first.")

    groups: dict[str, list[int]] = {}
    for rid, item in item_of.items():
        groups.setdefault(item, []).append(rid)
    positives = {tuple(sorted(p)) for ids in groups.values() for p in itertools.combinations(ids, 2)}
    retrieved = {(a, b) for a, b, *_ in pairs}

    report = {"rows": len(item_of), "items": len(groups), "true_pairs": len(positives),
              "candidate_recall": round(len(positives & retrieved) / len(positives), 4) if positives else 0.0,
              "thresholds": {}}
    for name in ("review_floor", "equivalent", "near", "auto_suggest"):
        t = th.get(name)
        if t is None:
            continue
        pred = {(a, b) for a, b, score, status, _ in pairs if status != "blocked" and score >= t}
        report["thresholds"][name] = {"value": t, **prf(pred, positives)}

    hn_blocked, hn_leaked = 0, []
    for a, b, score, status, mtype in pairs:
        key = negatives.get(frozenset((item_of[a], item_of[b])))
        if key is None:
            continue
        if status == "blocked":
            hn_blocked += 1
        else:
            hn_leaked.append({"key": key, "status": status, "score": score, "a": desc[a], "b": desc[b]})
    report["hard_negatives"] = {"retrieved": hn_blocked + len(hn_leaked), "blocked": hn_blocked,
                                "leaked": len(hn_leaked), "examples": hn_leaked[:10]}
    mix: dict[str, dict[str, int]] = {}
    for a, b, _, status, mtype in pairs:
        if status != "blocked":
            row = mix.setdefault(mtype, {"correct": 0, "wrong": 0})
            row["correct" if item_of[a] == item_of[b] else "wrong"] += 1
    report["match_types"] = mix

    floor, auto = report["thresholds"].get("review_floor", {}), report["thresholds"].get("auto_suggest", {})
    report["targets"] = {
        "G1_f1_at_review_floor": {"value": floor.get("f1"), "target": F1_TARGET,
                                  "met": (floor.get("f1") or 0) >= F1_TARGET},
        "G2_precision_at_auto": {"value": auto.get("precision"), "target": PRECISION_TARGET,
                                 "met": (auto.get("precision") or 0) >= PRECISION_TARGET or not auto.get("predicted")},
        "G2_hard_negatives_blocked": {"value": f"{hn_blocked}/{hn_blocked + len(hn_leaked)}", "met": not hn_leaked},
    }

    print(f"\nEkCode evaluation: {report['rows']} synthetic rows, {report['items']} items, "
          f"{report['true_pairs']} true duplicate pairs")
    print(f"candidate recall (true pairs retrieved by ANN top-15): {report['candidate_recall']:.1%}\n")
    print(f"{'threshold':<14}{'value':>7}{'pred':>7}{'TP':>7}{'prec':>8}{'recall':>8}{'F1':>8}")
    for name, m in report["thresholds"].items():
        print(f"{name:<14}{m['value']:>7.2f}{m['predicted']:>7}{m['true_positives']:>7}"
              f"{m['precision']:>8.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}")
    hn = report["hard_negatives"]
    print(f"\nhard negatives retrieved: {hn['retrieved']}, blocked: {hn['blocked']}, leaked: {hn['leaked']}")
    for ex in hn["examples"]:
        print(f"  LEAK [{ex['key']}] {ex['status']} {ex['score']:.3f}\n     {ex['a']}\n     {ex['b']}")
    print("\ntargets:")
    for name, t in report["targets"].items():
        print(f"  {'PASS' if t['met'] else 'FAIL'}  {name}: {t['value']} (target {t.get('target', 'all')})")

    out = folder / "eval_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nreport written to {out}")
    if args.strict and not all(t["met"] for t in report["targets"].values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
