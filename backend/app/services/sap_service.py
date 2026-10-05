"""SAP S/4HANA Product Master (API_PRODUCT_SRV) OData client.
Sandbox: register free at api.sap.com (SAP Business Accelerator Hub), open the Product Master API, copy your API key.
Verify entity/field names on api.sap.com before relying on them."""
import io

import httpx
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import CodeMapping, Cpse, NationalMaterial, RawMaterial


def _headers(api_key: str) -> dict:
    return {"APIKey": api_key, "Accept": "application/json"}


def test_connection(base_url: str, api_key: str) -> dict:
    try:
        r = httpx.get(f"{base_url}/A_Product", params={"$top": 3, "$format": "json"},
                      headers=_headers(api_key), timeout=20)
    except httpx.HTTPError as e:
        return {"ok": False, "status": None, "sample": f"connection failed: {e}"[:300]}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "sample": r.text[:300]}
    try:
        results = r.json().get("d", {}).get("results", [])[:3]
    except ValueError:
        return {"ok": False, "status": r.status_code, "sample": "the response was not JSON"}
    return {"ok": True, "status": 200, "sample": results}


PAGE = 500


def pull_products(base_url: str, api_key: str, top: int = 200) -> pd.DataFrame:
    """Pages through A_Product with $top/$skip (the service caps page sizes) and keeps English descriptions."""
    rows: dict[str, dict] = {}
    params = {"$format": "json", "$expand": "to_Description",
              "$select": "Product,BaseUnit,ProductGroup,to_Description/ProductDescription,to_Description/Language"}
    with httpx.Client(headers=_headers(api_key), timeout=60) as client:
        skip = 0
        while skip < top:
            size = min(PAGE, top - skip)
            r = client.get(f"{base_url.rstrip('/')}/A_Product", params={**params, "$top": size, "$skip": skip})
            r.raise_for_status()
            batch = r.json().get("d", {}).get("results", [])
            for p in batch:
                descs = [d.get("ProductDescription") for d in (p.get("to_Description") or {}).get("results", [])
                         if d.get("Language") == "EN" and d.get("ProductDescription")]
                if p.get("Product") and descs:
                    rows[p["Product"]] = {"MATNR": p["Product"], "MAKTX": descs[0], "MEINS": p.get("BaseUnit"),
                                          "MATKL": p.get("ProductGroup")}
            if len(batch) < size:
                break
            skip += size
    return pd.DataFrame(list(rows.values()), columns=["MATNR", "MAKTX", "MEINS", "MATKL"])  # header even when empty


def safe_cell(v):
    """Neutralize spreadsheet formula injection: openpyxl writes a string starting with "=" as a formula,
    and Excel evaluates =, +, - and @ at the start of a CSV cell."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def export_mapping(db: Session, cpse_code: str, fmt: str = "xlsx") -> bytes:
    cpse = db.query(Cpse).filter_by(code=cpse_code).first()
    if not cpse:
        raise HTTPException(404, "Unknown CPSE")
    q = (db.query(RawMaterial, CodeMapping, NationalMaterial)
         .join(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
         .join(NationalMaterial, NationalMaterial.nmc == CodeMapping.nmc)
         .filter(RawMaterial.cpse_id == cpse.id)
         .order_by(RawMaterial.legacy_code))
    df = pd.DataFrame([{"CPSE": cpse_code, "MATNR": r.legacy_code, "MAKTX": r.description, "MEINS": r.uom_raw,
                        "NMC": n.nmc, "NMC_DESCRIPTION": n.standard_description, "UNSPSC": n.unspsc,
                        "UOM_UNECE": n.uom_code, "CONFIDENCE": m.confidence, "NMC_STATUS": n.status}
                       for r, m, n in q],
                      columns=["CPSE", "MATNR", "MAKTX", "MEINS", "NMC", "NMC_DESCRIPTION", "UNSPSC", "UOM_UNECE",
                               "CONFIDENCE", "NMC_STATUS"])
    df = df.map(safe_cell)
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8-sig")      # BOM so Excel opens it as UTF-8
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="NMC_MAPPING")
    return buf.getvalue()
