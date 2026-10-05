import time
from pathlib import Path

import joblib
import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from . import FEATURE_KEYS, MIN_PER_CLASS, MIN_ROWS


def train(rows: list[tuple[dict, int]], out_dir: Path) -> dict:
    X = np.array([[f[k] for k in FEATURE_KEYS] for f, _ in rows])
    y = np.array([lbl for _, lbl in rows])
    counts = np.bincount(y, minlength=2) if len(y) else np.zeros(2, dtype=int)
    if len(rows) < MIN_ROWS or counts.min() < MIN_PER_CLASS:
        raise ValueError(f"Need at least {MIN_ROWS} labeled pairs with {MIN_PER_CLASS}+ approvals and "
                         f"{MIN_PER_CLASS}+ rejections (have {int(counts[1])} approved, {int(counts[0])} rejected)")
    clf = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10, verbose=-1)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pred = cross_val_predict(clf, X, y, cv=cv)
    metrics = {"precision": round(float(precision_score(y, pred, zero_division=0)), 4),
               "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
               "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
               "n": int(len(y)), "positives": int(counts[1])}
    clf.fit(X, y)
    version = time.strftime("v%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{version}.joblib"
    joblib.dump(clf, path)
    return {"version": version, "path": str(path), "metrics": metrics}
