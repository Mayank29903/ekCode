"""Import the GST HSN master (Excel from the GST portal / CBIC, e.g. HSN_SAC.xlsx) into
$DATA_DIR/reference/hsn.csv (hsn,description). HSN classification is optional in v1 (PRD FR7).

    python scripts/import_hsn_excel.py HSN_SAC.xlsx

Every sheet is scanned; the header row is found automatically (a cell mentioning "HSN" and one mentioning
"description"), because the official files have title rows above the table. SAC (services) codes are skipped.
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path

import pandas as pd


def find_table(raw: pd.DataFrame) -> pd.DataFrame | None:
    for i in range(min(len(raw), 15)):
        cells = [str(v).strip().lower() for v in raw.iloc[i].tolist()]
        code = next((j for j, c in enumerate(cells) if "hsn" in c and "desc" not in c), None)
        desc = next((j for j, c in enumerate(cells) if "desc" in c), None)
        if code is not None and desc is not None:
            body = raw.iloc[i + 1:, [code, desc]]
            body.columns = ["hsn", "description"]
            return body
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="HSN master .xlsx/.xls")
    ap.add_argument("--out", default=str(Path(os.getenv("DATA_DIR", "/data")) / "reference" / "hsn.csv"))
    args = ap.parse_args()
    src = Path(args.source)
    if not src.exists():
        sys.exit(f"{src} not found")

    codes: dict[str, str] = {}
    for name, raw in pd.read_excel(src, sheet_name=None, header=None, dtype=str).items():
        table = find_table(raw.fillna(""))
        if table is None:
            print(f"  sheet {name!r}: no HSN table found, skipped")
            continue
        before = len(codes)
        for code, desc in table.itertuples(index=False):
            code = re.sub(r"\D", "", str(code))
            desc = re.sub(r"\s+", " ", str(desc)).strip()
            if len(code) in (2, 4, 6, 8) and not code.startswith("99") and desc:   # 99xx = SAC (services)
                codes.setdefault(code, desc)
        print(f"  sheet {name!r}: {len(codes) - before} codes")
    if not codes:
        sys.exit("No HSN codes found")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["hsn", "description"])
        w.writerows(sorted(codes.items()))
    by_len = {n: sum(1 for c in codes if len(c) == n) for n in (2, 4, 6, 8)}
    print(f"wrote {len(codes)} HSN codes to {out} (chapters {by_len[2]}, headings {by_len[4]}, "
          f"sub-headings {by_len[6]}, tariff items {by_len[8]})")


if __name__ == "__main__":
    main()
