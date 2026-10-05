"""Load the generated seed files through the real ingestion pipeline (ADR-15), labelled source='synthetic'.

    python scripts/load_seed.py                          # ingest every seed_<CPSE>.csv in-process
    python scripts/load_seed.py --queue                  # hand the files to the RQ worker instead (watch in the UI)
    python scripts/load_seed.py --simulate-review 0.5    # then decide half the open suggestions from the ground truth
    python scripts/load_seed.py --promote-singletons     # and issue codes for the unique materials

--simulate-review plays a careful steward using truth.csv, so the demo has approvals, rejections, national codes and
enough labels to retrain the model. Those decisions are audited with actor "system" and reason "simulated".
"""
import argparse
import csv
import os
import random
import sys
from pathlib import Path

from fastapi import HTTPException

from app.db import SessionLocal
from app.init_db import main as init_db
from app.models import Cpse, IngestJob, MatchPair, RawMaterial
from app.services.cluster_service import approve_pair, promote_singletons, reject_pair
from app.services.ingest_service import REQUIRED, auto_map, read_table, run_pipeline
from app.settings_store import get_setting
from app.workers.queue import queue
from ekml.normalize import set_abbreviations


def ingest_file(path: Path, code: str, use_queue: bool) -> None:
    with SessionLocal() as db:
        cpse = db.query(Cpse).filter_by(code=code).first()
        if not cpse:
            print(f"  skip {path.name}: CPSE {code} is not seeded")
            return
        df = read_table(path)
        mapping = auto_map(list(df.columns))
        if missing := [f for f in REQUIRED if f not in mapping]:
            print(f"  skip {path.name}: could not map {missing} from columns {list(df.columns)}")
            return
        job = IngestJob(cpse_id=cpse.id, filename=path.name, path=str(path), source="synthetic", status="queued",
                        stage="queued", column_map=mapping, total_rows=len(df))
        db.add(job)
        db.commit()
        if use_queue:
            queue.enqueue("app.workers.jobs.ingest_job", str(job.id), job_timeout=7200)
            print(f"  queued {path.name} ({len(df)} rows) as job {job.id}")
            return
        run_pipeline(db, job)
        report = job.report or {}
        print(f"  {path.name}: {report.get('valid_rows', 0)} rows, {report.get('new_or_changed', 0)} new/changed, "
              f"{job.error_rows} errors")


def load_truth(folder: Path) -> dict[tuple[str, str], str]:
    with (folder / "truth.csv").open(encoding="utf-8", newline="") as fh:
        return {(r["cpse"], r["legacy_code"]): r["item_id"] for r in csv.DictReader(fh)}


def simulate_review(folder: Path, fraction: float, seed: int) -> None:
    truth = load_truth(folder)
    with SessionLocal() as db:
        item_of = {rid: truth[(code, legacy)] for rid, code, legacy in
                   db.query(RawMaterial.id, Cpse.code, RawMaterial.legacy_code)
                   .join(Cpse, Cpse.id == RawMaterial.cpse_id).filter(RawMaterial.source == "synthetic")
                   if (code, legacy) in truth}
        open_ids = [pid for pid, a, b in db.query(MatchPair.id, MatchPair.a_id, MatchPair.b_id)
                    .filter(MatchPair.status == "suggested") if a in item_of and b in item_of]
        random.Random(seed).shuffle(open_ids)
        approved = rejected = conflicts = 0
        for pid in open_ids[:round(len(open_ids) * fraction)]:
            p = db.query(MatchPair).filter_by(id=pid).with_for_update().first()
            try:
                if item_of[p.a_id] == item_of[p.b_id]:
                    approve_pair(db, p, None, "simulated steward decision (ground truth)")
                    approved += 1
                else:
                    reject_pair(db, p, None, "simulated steward decision (ground truth)")
                    rejected += 1
                db.commit()
            except HTTPException:
                db.rollback()
                conflicts += 1
        print(f"simulated review: {approved} approved, {rejected} rejected, {conflicts} skipped "
              f"(of {len(open_ids)} open synthetic suggestions)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(Path(os.getenv("DATA_DIR", "/data")) / "seed"))
    ap.add_argument("--queue", action="store_true", help="enqueue to the RQ worker instead of running in-process")
    ap.add_argument("--simulate-review", type=float, default=0.0, metavar="FRACTION",
                    help="decide this fraction (0-1) of open synthetic suggestions from truth.csv")
    ap.add_argument("--promote-singletons", action="store_true", help="issue NMCs for unique materials afterwards")
    ap.add_argument("--skip-ingest", action="store_true", help="only run --simulate-review / --promote-singletons")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    folder = Path(args.dir)
    files = sorted(folder.glob("seed_*.csv"))
    if not files:
        sys.exit(f"No seed_*.csv in {folder}. Run scripts/generate_cpse_seed.py first.")
    init_db()
    with SessionLocal() as db:
        set_abbreviations(get_setting(db, "abbreviations"))     # empty -> the shipped YAML
    if not args.skip_ingest:
        print(f"loading {len(files)} files from {folder}")
        for path in files:
            ingest_file(path, path.stem.split("_", 1)[1].upper(), args.queue)
        if args.queue and (args.simulate_review or args.promote_singletons):
            print("--queue: when the worker has finished, run again with --skip-ingest to review / promote")
            return
    if args.simulate_review:
        simulate_review(folder, max(0.0, min(1.0, args.simulate_review)), args.seed)
    if args.promote_singletons:
        with SessionLocal() as db:
            print(f"issued {promote_singletons(db, None)} national codes for unique materials")


if __name__ == "__main__":
    main()
