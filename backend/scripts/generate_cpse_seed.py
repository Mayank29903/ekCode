"""Generate realistic, messy CPSE material-master exports plus the ground truth to score EkCode against.

Each CPSE gets its own file layout (header names, delimiter, code format, unit words) and its own habits for
writing descriptions (abbreviations, word order, inch vs NB, grade spellings). Items that differ in exactly one
critical attribute (M12 vs M16, 150# vs 300#, SS304 vs SS316, copper vs aluminium) are recorded as hard negatives.

    python scripts/generate_cpse_seed.py                 # -> $DATA_DIR/seed/seed_<CPSE>.csv, truth.csv, hard_negatives.csv
    python scripts/generate_cpse_seed.py --items 400 --seed 7

Rows are loaded with source='synthetic' by scripts/load_seed.py and show a "Synthetic" badge in the UI (ADR-15).
"""
import argparse
import csv
import itertools
import os
import random
from pathlib import Path

# ---- CPSE file layouts -------------------------------------------------------------------------------------------

CPSES = {
    "IOCL": {"header": ["Material", "Material Description", "Base Unit", "Unit Price", "Annual Qty"], "sep": ",",
             "code": lambda n: f"{10040000 + n}", "each": "NOS", "metre": "MTR", "price": 1.00, "style": 0},
    "ONGC": {"header": ["MATNR", "MAKTX", "MEINS", "NETPR", "Consumption"], "sep": ",",
             "code": lambda n: f"{3000000 + n}", "each": "EA", "metre": "M", "price": 0.95, "style": 1},
    "BPCL": {"header": ["Item Code", "Item Description", "UOM", "Rate", "Quantity"], "sep": ";",
             "code": lambda n: f"MT-{80000 + n}", "each": "PCS", "metre": "MTRS", "price": 1.05, "style": 2},
    "HPCL": {"header": ["Material No", "Short Text", "Unit", "Last Price", "Annual Consumption"], "sep": "\t",
             "code": lambda n: f"HP{n:06d}", "each": "NO", "metre": "METRE", "price": 1.10, "style": 3},
    "GAIL": {"header": ["material_code", "material_description", "unit_of_measure", "unit_price", "annual_quantity"],
             "sep": ",", "code": lambda n: f"G{n:07d}", "each": "Nos", "metre": "Mtr", "price": 0.98, "style": 0},
    "NTPC": {"header": ["Code", "Description", "UoM", "Price", "Qty"], "sep": "|",
             "code": lambda n: f"NT-{n:05d}", "each": "EACH", "metre": "M", "price": 1.02, "style": 1},
}

# ---- how people write values -------------------------------------------------------------------------------------

NPS_TO_DN = {0.5: 15, 0.75: 20, 1: 25, 1.5: 40, 2: 50, 3: 80, 4: 100, 6: 150, 8: 200, 10: 250, 12: 300}
FRACTIONS = {0.25: "1/4", 0.5: "1/2", 0.75: "3/4"}
GRADE_VARIANTS = {
    "A105": ["A105", "A-105", "ASTM A105", "A 105"],
    "WCB": ["WCB", "A216 WCB", "ASTM A216 GR WCB"],
    "CF8M": ["CF8M", "CF-8M", "ASTM A351 CF8M"],
    "A106B": ["A106 GR.B", "A106B", "ASTM A106 GR B", "A-106 GR.B"],
    "A193B7": ["A193 B7", "A193-B7", "ASTM A193 GR B7"],
}


def inch(v: float) -> str:
    """0.5 -> 1/2 ; 1.5 -> 1-1/2 ; 2 -> 2"""
    whole, frac = int(v), round(v - int(v), 2)
    if not frac:
        return str(whole)
    return FRACTIONS[frac] if whole == 0 else f"{whole}-{FRACTIONS[frac]}"


def num(v) -> str:
    return f"{v:g}"


def grade(g: str, rng: random.Random, can_drop: bool = False) -> str:
    if g.startswith("SS"):
        n = g[2:]
        if can_drop and rng.random() < 0.15:
            return "SS"                                  # "Bolt hexagonal SS 12x50mm": grade not stated
        return rng.choice([f"SS{n}", f"SS {n}", f"S.S.{n}", f"S/S {n}", f"{n} SS"])
    return rng.choice(GRADE_VARIANTS[g])


# ---- families: attribute domains, description styles, price, quantity --------------------------------------------

def r_bolt(a, s, rng, drop):
    g, d, L = grade(a["grade"], rng, drop), a["thread"], a["length_mm"]
    return [f"HEX BOLT M{d}X{L} {g}", f"Bolt hexagonal {g} {d}x{L}mm", f"{g} HX BLT M{d} L{L}",
            f"BOLT,HEX,M{d} X {L}MM,{g}", f"HEX HD BOLT M{d} X {L} LG {g}"][s % 5]


def r_stud(a, s, rng, drop):
    g, d, L = grade(a["grade"], rng), a["thread"], a["length_mm"]
    return [f"STUD BOLT M{d}X{L} {g}", f"STUD BLT M{d} X {L}MM {g} WITH 2 NUTS", f"BOLT,STUD,M{d}X{L},{g}",
            f"STUD M{d} X {L} {g}"][s % 4]


def r_nut(a, s, rng, drop):
    g, d = grade(a["grade"], rng, drop), a["thread"]
    return [f"HEX NUT M{d} {g}", f"NUT HEX M{d} {g}", f"HX NUT M-{d} {g}", f"NUT,HEXAGONAL,M{d},{g}"][s % 4]


def r_gasket(a, s, rng, drop):
    g, sz, r = grade(a["grade"], rng), a["size_in"], a["rating"]
    return [f"SPIRAL WOUND GASKET {inch(sz)} IN {r}# {g} ASME B16.20", f'SPWD GSKT {inch(sz)}" {r}# {g} B16.20',
            f"GASKET SPW {NPS_TO_DN[sz]}NB CL{r} {g}", f"GASKET,SPIRAL WOUND,{inch(sz)} INCH,CLASS {r},{g}"][s % 4]


def r_gate(a, s, rng, drop):
    b, sz, r = grade(a["grade"], rng), a["size_in"], a["rating"]
    return [f'GATE VALVE {inch(sz)}" {r}# {b} API 600', f"GV {inch(sz)} IN {r}# {b} API 600",
            f"VALVE,GATE,{NPS_TO_DN[sz]}NB,CL{r},BODY {b},API600", f"VALVE GATE {inch(sz)}INCH {r}LB {b}"][s % 4]


def r_ball(a, s, rng, drop):
    b, sz, r = grade(a["grade"], rng), a["size_in"], a["rating"]
    return [f'BALL VALVE {inch(sz)}" {r}# {b} API 6D', f"BV {inch(sz)} IN {r}# {b} API 6D",
            f"VALVE,BALL,{NPS_TO_DN[sz]}NB,CL{r},{b},API 6D", f"BALL VLV {inch(sz)}INCH CL{r} {b}"][s % 4]


def r_pipe(a, s, rng, drop):
    g, sz, sch = grade(a["grade"], rng), a["size_in"], a["schedule"]
    return [f'PIPE {inch(sz)}" SCH {sch} SMLS {g}', f"PIPE CS SMLS {NPS_TO_DN[sz]}NB SCH{sch} {g}",
            f"PIPE,SMLS,{inch(sz)} IN,SCH-{sch},{g}", f"SEAMLESS PIPE {NPS_TO_DN[sz]} NB SCH {sch} {g}"][s % 4]


def r_bearing(a, s, rng, drop):
    b = a["bearing_no"]
    no, _, suffix = b.partition("-")
    return [f"BALL BEARING {b}", f"BRG {no} {suffix}".strip(), f"BEARING,BALL,{no} {suffix}".strip(" ,"),
            f"DEEP GROOVE BALL BEARING {no}{suffix}"][s % 4]


def r_cable(a, s, rng, drop):
    c, ar, cu = num(a["cores"]), num(a["area_sqmm"]), a["conductor"] == "COPPER"
    short, word = ("CU", "COPPER") if cu else ("AL", "ALUMINIUM")
    return [f"CABLE {c}C X {ar} SQMM {short} XLPE ARM 1.1KV", f"CBL {c} CORE X {ar} SQ MM {word} 1.1 KV XLPE",
            f"POWER CABLE,{c}C X {ar}SQMM,{short},XLPE,ARMOURED,1.1KV",
            f"{c}C X {ar} SQMM {short} ARMOURED CABLE 1.1KV"][s % 4]


FAMILIES = {
    "BOLT": dict(render=r_bolt, unit="each", qty=(100, 5000),
                 domains={"thread": [8, 10, 12, 16, 20, 24], "length_mm": [25, 40, 50, 65, 80, 100],
                          "grade": ["SS304", "SS316"]},
                 price=lambda a: (5 + a["thread"] * a["length_mm"] / 30) * (1.35 if a["grade"] == "SS316" else 1)),
    "STUD BOLT": dict(render=r_stud, unit="each", qty=(50, 2000),
                      domains={"thread": [16, 20, 24], "length_mm": [90, 110, 130], "grade": ["A193B7"]},
                      price=lambda a: 20 + a["thread"] * a["length_mm"] / 25),
    "NUT": dict(render=r_nut, unit="each", qty=(200, 8000),
                domains={"thread": [8, 10, 12, 16, 20, 24], "grade": ["SS304", "SS316"]},
                price=lambda a: (2 + a["thread"] * 0.4) * (1.35 if a["grade"] == "SS316" else 1)),
    "GASKET": dict(render=r_gasket, unit="each", qty=(20, 800),
                   domains={"size_in": [0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8], "rating": [150, 300, 600],
                            "grade": ["SS304", "SS316"]},
                   price=lambda a: (150 + a["size_in"] * 120 * (a["rating"] / 150) ** 0.5)
                   * (1.2 if a["grade"] == "SS316" else 1)),
    "GATE VALVE": dict(render=r_gate, unit="each", qty=(2, 60),
                       domains={"size_in": [2, 3, 4, 6, 8], "rating": [150, 300, 600], "grade": ["WCB", "A105"]},
                       price=lambda a: 6000 * a["size_in"] * (a["rating"] / 150) ** 0.6),
    "BALL VALVE": dict(render=r_ball, unit="each", qty=(2, 80),
                       domains={"size_in": [1, 1.5, 2, 3, 4, 6], "rating": [150, 300],
                                "grade": ["A105", "WCB", "CF8M"]},
                       price=lambda a: 5000 * a["size_in"] * (a["rating"] / 150) ** 0.6
                       * (1.8 if a["grade"] == "CF8M" else 1)),
    "PIPE": dict(render=r_pipe, unit="metre", qty=(100, 5000),
                 domains={"size_in": [0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8], "schedule": [40, 80, 160],
                          "grade": ["A106B"]},
                 price=lambda a: 300 * a["size_in"] * a["schedule"] / 40),
    "BEARING": dict(render=r_bearing, unit="each", qty=(10, 300),
                    domains={"bearing_no": [f"{n}{s}" for n in (6204, 6205, 6206, 6305, 6308, 6310)
                                            for s in ("", "-2RS", "-ZZ")]},
                    price=lambda a: 150 + int(a["bearing_no"][2:4]) * 30 + (40 if "-" in a["bearing_no"] else 0)),
    "CABLE": dict(render=r_cable, unit="metre", qty=(200, 8000),
                  domains={"cores": [2, 3, 3.5, 4], "area_sqmm": [2.5, 4, 16, 25, 95, 185],
                           "conductor": ["COPPER", "ALUMINIUM"]},
                  price=lambda a: 30 * a["cores"] * a["area_sqmm"] / 10 * (1 if a["conductor"] == "COPPER" else 0.4)),
}

# Items without extractable attributes: matching relies on meaning and wording alone.
MISC = [
    ("GREASE LITHIUM EP2", ["GREASE LITHIUM BASE EP-2 18KG", "LITHIUM GREASE EP2 18 KG BUCKET",
                            "GREASE,EP2,LITHIUM COMPLEX,18KG"], 4200, "each", (10, 300)),
    ("SAFETY HELMET", ["SAFETY HELMET INDUSTRIAL WITH RATCHET", "HELMET SAFETY HDPE RATCHET TYPE",
                       "INDUSTRIAL SAFETY HELMET IS 2925"], 350, "each", (50, 2000)),
    ("V BELT B52", ["V BELT B-52", "V-BELT SIZE B52", "BELT,V,B 52"], 420, "each", (20, 400)),
    ("ELECTRODE E6013 3.15", ["WELDING ELECTRODE E6013 3.15MM", "ELECTRODE E-6013 DIA 3.15 MM",
                              "E6013 WELDING ROD 3.15MM"], 9, "each", (1000, 20000)),
    ("HYDRAULIC FILTER 10 MICRON", ["HYDRAULIC FILTER ELEMENT 10 MICRON", "FILTER ELEMENT,HYDRAULIC,10MIC",
                                    "ELEMENT FILTER HYD 10 MICRON"], 2600, "each", (5, 120)),
    ("PVC INSULATION TAPE 19MM", ["PVC INSULATION TAPE 19MM", "TAPE INSULATION PVC 19 MM X 8 M",
                                  "INSULATING TAPE PVC 19MM"], 25, "each", (100, 5000)),
]


def item_id(noun: str, attrs: dict) -> str:
    return noun + "|" + "|".join(f"{k}={num(v) if isinstance(v, float) else v}" for k, v in sorted(attrs.items()))


def build_catalog(rng: random.Random, n_items: int) -> list[dict]:
    pools = {noun: [dict(zip(f["domains"], combo)) for combo in itertools.product(*f["domains"].values())]
             for noun, f in FAMILIES.items()}
    total = sum(len(p) for p in pools.values())
    items = []
    for noun, pool in pools.items():
        for attrs in rng.sample(pool, max(1, min(len(pool), round(len(pool) * n_items / total)))):
            items.append({"id": item_id(noun, attrs), "noun": noun, "attrs": attrs,
                          "price": FAMILIES[noun]["price"](attrs), "unit": FAMILIES[noun]["unit"],
                          "qty": FAMILIES[noun]["qty"]})
    for name, variants, price, unit, qty in MISC:
        items.append({"id": f"MISC|{name}", "noun": None, "variants": variants, "price": price, "unit": unit,
                      "qty": qty})
    return items


def hard_negatives(items: list[dict]) -> list[tuple[str, str, str]]:
    """Every pair of catalogue items of the same kind that differ in exactly one attribute."""
    out = []
    by_noun: dict[str, list[dict]] = {}
    for it in items:
        if it["noun"]:
            by_noun.setdefault(it["noun"], []).append(it)
    for group in by_noun.values():
        for x, y in itertools.combinations(group, 2):
            diff = [k for k in x["attrs"] if x["attrs"][k] != y["attrs"][k]]
            if len(diff) == 1:
                out.append((x["id"], y["id"], diff[0]))
    return out


def describe(item: dict, style: int, rng: random.Random, can_drop_grade: bool) -> str:
    if item["noun"] is None:
        text = item["variants"][style % len(item["variants"])]
    else:
        text = FAMILIES[item["noun"]]["render"](item["attrs"], style, rng, can_drop_grade)
    roll = rng.random()                                   # house style noise
    if roll < 0.80:
        text = text.upper()
    elif roll < 0.88:
        text = text.lower()
    if rng.random() < 0.10:
        text = text.replace(" ", "  ", 1)
    if rng.random() < 0.05:
        text += "."
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(os.getenv("DATA_DIR", "/data")) / "seed"))
    ap.add_argument("--items", type=int, default=240, help="catalogue items with attributes (plus a few misc)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cpses", default=",".join(CPSES), help="comma-separated subset of " + ",".join(CPSES))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    cpses = [c.strip().upper() for c in args.cpses.split(",") if c.strip().upper() in CPSES]
    items = build_catalog(rng, args.items)
    negatives = hard_negatives(items)
    # Never drop the one attribute that tells an item apart from its hard-negative sibling.
    protected = {}
    for a, b, key in negatives:
        protected.setdefault(a, set()).add(key)
        protected.setdefault(b, set()).add(key)

    rows: dict[str, list[list]] = {c: [] for c in cpses}
    truth, counters = [], {c: 0 for c in cpses}

    def add_row(cpse: str, item: dict, style: int):
        spec = CPSES[cpse]
        counters[cpse] += 1
        code = spec["code"](counters[cpse])
        desc = describe(item, style, rng, "grade" not in protected.get(item["id"], set()))
        unit = spec[item["unit"]]
        price = round(item["price"] * spec["price"] * rng.uniform(0.9, 1.1), 2)
        qty = rng.randint(*item["qty"])
        rows[cpse].append([code, desc, unit, price, qty])
        truth.append({"cpse": cpse, "legacy_code": code, "item_id": item["id"], "noun": item["noun"] or ""})

    for item in items:
        holders = rng.sample(cpses, min(len(cpses), rng.choices([1, 2, 3, 4, 5], weights=[20, 30, 25, 15, 10])[0]))
        for cpse in holders:
            house = CPSES[cpse]["style"]
            add_row(cpse, item, house if rng.random() < 0.6 else rng.randrange(5))
            if rng.random() < 0.04:                        # the same item twice inside one CPSE
                add_row(cpse, item, house + 1 + rng.randrange(3))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for cpse, lines in rows.items():
        rng.shuffle(lines)
        spec = CPSES[cpse]
        with (out / f"seed_{cpse}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=spec["sep"])
            w.writerow(spec["header"])
            w.writerows(lines)
    with (out / "truth.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["cpse", "legacy_code", "item_id", "noun"])
        w.writeheader()
        w.writerows(truth)
    with (out / "hard_negatives.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["item_a", "item_b", "key"])
        w.writerows(negatives)

    shared = sum(1 for it in items if sum(t["item_id"] == it["id"] for t in truth) > 1)
    print(f"wrote {sum(len(v) for v in rows.values())} rows for {len(cpses)} CPSEs into {out}")
    for cpse in cpses:
        print(f"  seed_{cpse}.csv  {len(rows[cpse]):4d} rows")
    print(f"  {len(items)} distinct items, {shared} held by more than one row, {len(negatives)} hard-negative pairs")


if __name__ == "__main__":
    main()
