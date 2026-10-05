"""Evaluate the EkCode scorer on the public WDC Products benchmark (Web Data Commons product matching).

Download a split from https://webdatacommons.org/largescaleproductcorpus/wdc-products/ (JSON lines, gzipped),
for example wdcproducts80cc20rnd000un_test.json.gz, then:

    python scripts/load_wdc_benchmark.py wdcproducts80cc20rnd000un_test.json.gz
    python scripts/load_wdc_benchmark.py pairs.jsonl --left title_left --right title_right --label label

No database is needed. WDC offers are consumer products, so the industrial hard gates rarely fire; the
benchmark measures the semantic + lexical part of the scorer against an independent, public ground truth.
"""
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

import numpy as np

from app.init_db import DEFAULTS
from ekml.embed import embed
from ekml.extract import extract
from ekml.features import pair_features
from ekml.gates import gate_failures
from ekml.normalize import normalize
from ekml.score import decide


def read_records(path: Path, limit: int) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        head = fh.read(1)
        fh.seek(0)
        if head == "[":
            return json.load(fh)[:limit]
        out = []
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
                if len(out) >= limit:
                    break
        return out


def prf(pred: np.ndarray, y: np.ndarray) -> dict:
    tp = int((pred & y).sum())
    p = tp / pred.sum() if pred.sum() else 0.0
    r = tp / y.sum() if y.sum() else 0.0
    return {"precision": round(float(p), 4), "recall": round(float(r), 4),
            "f1": round(float(2 * p * r / (p + r)) if p + r else 0.0, 4), "predicted": int(pred.sum())}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--left", default="title_left")
    ap.add_argument("--right", default="title_right")
    ap.add_argument("--label", default="label")
    ap.add_argument("--out", default=str(Path(os.getenv("DATA_DIR", "/data")) / "benchmarks"))
    args = ap.parse_args()
    path = Path(args.path)
    if not path.exists():
        sys.exit(f"{path} not found")

    recs = [r for r in read_records(path, args.limit) if r.get(args.left) and r.get(args.right)
            and str(r.get(args.label)) in ("0", "1")]
    if not recs:
        sys.exit(f"No usable pairs: need fields {args.left!r}, {args.right!r} and a 0/1 {args.label!r}")
    print(f"{len(recs)} pairs from {path.name} ({sum(str(r[args.label]) == '1' for r in recs)} matches)")

    texts = sorted({str(r[k]) for r in recs for k in (args.left, args.right)})
    norm = {t: normalize(t) for t in texts}
    attrs = {t: extract(norm[t])[0] for t in texts}
    vecs = dict(zip(texts, embed([norm[t] or t.lower() for t in texts])))

    th = DEFAULTS["thresholds"]
    scores, gated, y = [], [], []
    for r in recs:
        a, b = str(r[args.left]), str(r[args.right])
        f = pair_features(float(vecs[a] @ vecs[b]), norm[a], norm[b], attrs[a], attrs[b], None, None)
        gates = gate_failures(attrs[a], attrs[b])
        scores.append(decide(f, gates, th).score)
        gated.append(bool(gates))
        y.append(str(r[args.label]) == "1")
    scores, gated, y = np.array(scores), np.array(gated), np.array(y)

    sweep = {f"{t:.2f}": prf((scores >= t) & ~gated, y) for t in np.arange(0.50, 0.96, 0.05)}
    best = max(sweep.items(), key=lambda kv: kv[1]["f1"])
    report = {"file": path.name, "pairs": len(recs), "matches": int(y.sum()),
              "at_review_floor": prf((scores >= th["review_floor"]) & ~gated, y),
              "at_near": prf((scores >= th["near"]) & ~gated, y),
              "best": {"threshold": best[0], **best[1]}, "sweep": sweep,
              "gates": {"negatives_blocked": int((gated & ~y).sum()), "positives_blocked": int((gated & y).sum())}}

    print(f"{'threshold':<10}{'prec':>8}{'recall':>8}{'F1':>8}{'pred':>8}")
    for t, m in sweep.items():
        print(f"{t:<10}{m['precision']:>8.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}{m['predicted']:>8}")
    print(f"best F1 {report['best']['f1']:.3f} at {report['best']['threshold']}; "
          f"gates blocked {report['gates']['negatives_blocked']} non-matches and "
          f"{report['gates']['positives_blocked']} true matches")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"wdc_{path.name.split('.')[0]}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report written to {target}")


if __name__ == "__main__":
    main()
