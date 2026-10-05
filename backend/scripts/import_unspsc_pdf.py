"""Import the free UNSPSC code list into $DATA_DIR/reference/unspsc.csv (code,title) for FR7 classification.

Accepts the PDF code list, or the Excel/CSV download (columns such as "Commodity" + "Commodity Title").
Afterwards the commodity titles are embedded once and cached next to the CSV, so the first approval that
classifies a material does not stall. Restart api and worker afterwards so they pick up the new list.

    python scripts/import_unspsc_pdf.py /data/reference/UNSPSC_English.pdf
    python scripts/import_unspsc_pdf.py unspsc.xlsx --no-embed
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path

CODE8 = re.compile(r"^\s*(\d{8})\s+(.+?)\s*$")                           # 31161500 Bolts
SPACED = re.compile(r"^\s*(\d{2})\s(\d{2})\s(\d{2})\s(\d{2})\s+(.+?)\s*$")   # 31 16 15 00 Bolts


def _title(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip(" .-")


def from_pdf(path: Path) -> dict[str, str]:
    import pdfplumber
    out: dict[str, str] = {}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if m := CODE8.match(line) or SPACED.match(line):
                    *parts, title = m.groups()
                    if title := _title(title):
                        out.setdefault("".join(parts), title)
    return out


def from_table(path: Path) -> dict[str, str]:
    import pandas as pd
    frames = (pd.read_excel(path, dtype=str, sheet_name=None).values() if path.suffix.lower() in (".xlsx", ".xls")
              else [pd.read_csv(path, dtype=str)])
    out: dict[str, str] = {}
    for df in frames:
        df = df.fillna("")
        cols = {c.strip().lower(): c for c in df.columns}
        # "Segment"/"Segment Title", "Family"/"Family Title", ... "Commodity"/"Commodity Title"
        pairs = [(cols[k], cols[f"{k} title"]) for k in cols if f"{k} title" in cols]
        if not pairs:
            code = next((c for k, c in cols.items() if "code" in k), None)
            title = next((c for k, c in cols.items() if any(w in k for w in ("title", "name", "description"))), None)
            pairs = [(code, title)] if code and title else []
        for code_col, title_col in pairs:
            for code, title in zip(df[code_col], df[title_col]):
                code = re.sub(r"\D", "", code)
                if len(code) == 8 and (title := _title(title)):
                    out.setdefault(code, title)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="UNSPSC PDF, XLSX or CSV")
    ap.add_argument("--out", default=str(Path(os.getenv("DATA_DIR", "/data")) / "reference" / "unspsc.csv"))
    ap.add_argument("--no-embed", action="store_true", help="skip pre-computing title embeddings")
    args = ap.parse_args()

    src, out = Path(args.source), Path(args.out)
    if not src.exists():
        sys.exit(f"{src} not found")
    codes = from_pdf(src) if src.suffix.lower() == ".pdf" else from_table(src)
    if not codes:
        sys.exit("No 8-digit UNSPSC codes found. Is this the code list (not the user guide)?")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "title"])
        w.writerows(sorted(codes.items()))
    for stale in out.parent.glob(f"{out.stem}*.npy"):        # embedding caches of the previous list
        stale.unlink(missing_ok=True)
    commodities = sum(1 for c in codes if not c.endswith("00"))
    print(f"wrote {len(codes)} codes ({commodities} commodities) to {out}")

    if args.no_embed:
        return
    from ekml import taxonomy
    if taxonomy.REF.resolve() != out.resolve():
        print(f"not embedding: the app reads {taxonomy.REF}; set DATA_DIR or --out to match")
        return
    print(f"embedded {taxonomy.warm()} commodity titles into {taxonomy.cache_path()}")
    print("running api and worker pick up the new list automatically (the index follows the file's timestamp)")


if __name__ == "__main__":
    main()
