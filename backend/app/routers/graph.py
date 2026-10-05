from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, defer

from ..db import contains, get_db
from ..models import CodeMapping, Cpse, MatchPair, NationalMaterial, RawMaterial
from ..security import current_user
from .materials import material_out, member_stats

router = APIRouter(tags=["graph"])


@router.get("/graph")
def graph_start(q: str | None = None, limit: int = Query(12, ge=1, le=50),
                db: Session = Depends(get_db), _=Depends(current_user)):
    """Starting points for the graph view: the most connected active national codes (optionally filtered)."""
    s = member_stats()
    query = (db.query(NationalMaterial, s.c.legacy_count, s.c.cpse_count, s.c.spend, s.c.synthetic, s.c.cpses)
             .join(s, s.c.nmc == NationalMaterial.nmc).filter(NationalMaterial.status == "active"))
    if q:
        pat = contains(q)
        query = query.filter(or_(NationalMaterial.nmc.ilike(pat, escape="\\"),
                                 NationalMaterial.standard_description.ilike(pat, escape="\\")))
    rows = query.order_by(s.c.cpse_count.desc(), s.c.legacy_count.desc(), NationalMaterial.nmc).limit(limit).all()
    return {"items": [material_out(*row) for row in rows]}


@router.get("/graph/{nmc}")
def graph(nmc: str, db: Session = Depends(get_db), _=Depends(current_user)):
    """FR10: NMC <-> legacy codes <-> CPSEs <-> standard <-> category, plus successors and open/blocked neighbours."""
    nm = db.get(NationalMaterial, nmc.strip().upper())
    if not nm:
        raise HTTPException(404, "National material not found")
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def node(nid: str, kind: str, label: str, **data) -> str:
        nodes.setdefault(nid, {"id": nid, "type": kind, "label": label, "data": data})
        return nid

    def edge(source: str, target: str, kind: str, **data) -> None:
        eid = f"{source}->{target}:{kind}" + (f"#{data['pair_id']}" if "pair_id" in data else "")
        edges.setdefault(eid, {"id": eid, "source": source, "target": target, "type": kind, "data": data})

    center = node(f"nmc:{nm.nmc}", "nmc" if nm.status == "active" else "deprecated", nm.nmc,
                  description=nm.standard_description, status=nm.status, attributes=nm.attributes or {}, center=True)

    members = (db.query(RawMaterial, Cpse.code, CodeMapping.confidence).options(defer(RawMaterial.embedding))
               .join(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
               .join(Cpse, Cpse.id == RawMaterial.cpse_id)
               .filter(CodeMapping.nmc == nm.nmc).all())
    member_ids = {r.id for r, _, _ in members}
    for r, code, confidence in members:
        lid = node(f"legacy:{r.id}", "legacy", r.legacy_code, cpse=code, description=r.description,
                   source=r.source, raw_id=r.id)
        edge(lid, center, "maps_to", confidence=confidence)
        edge(node(f"cpse:{code}", "cpse", code), lid, "owns")

    attrs = nm.attributes or {}
    if std := attrs.get("standard"):
        edge(center, node(f"standard:{std}", "standard", std), "conforms_to")
    if nm.noun:
        edge(center, node(f"category:{nm.noun}", "category", nm.noun), "is_a")
    if nm.unspsc:
        edge(center, node(f"unspsc:{nm.unspsc}", "unspsc", nm.unspsc), "classified_as")
    if nm.successor_nmc:
        edge(center, node(f"nmc:{nm.successor_nmc}", "nmc", nm.successor_nmc), "succeeded_by")
    for (old,) in db.query(NationalMaterial.nmc).filter(NationalMaterial.successor_nmc == nm.nmc):
        edge(node(f"nmc:{old}", "deprecated", old), center, "succeeded_by")

    if member_ids:   # open suggestions and blocked look-alikes that leave this cluster
        pairs = (db.query(MatchPair)
                 .filter(or_(MatchPair.a_id.in_(member_ids), MatchPair.b_id.in_(member_ids)),
                         MatchPair.status.in_(["suggested", "blocked"]))
                 .order_by(MatchPair.score.desc()).limit(20).all())
        outside = {p.b_id if p.a_id in member_ids else p.a_id for p in pairs} - member_ids
        others = {r.id: (r, code, m) for r, code, m in
                  db.query(RawMaterial, Cpse.code, CodeMapping.nmc).options(defer(RawMaterial.embedding))
                  .join(Cpse, Cpse.id == RawMaterial.cpse_id)
                  .outerjoin(CodeMapping, CodeMapping.raw_material_id == RawMaterial.id)
                  .filter(RawMaterial.id.in_(outside))} if outside else {}
        for p in pairs:
            mine, theirs = (p.a_id, p.b_id) if p.a_id in member_ids else (p.b_id, p.a_id)
            if theirs not in others:
                continue
            r, code, other_nmc = others[theirs]
            target = (node(f"nmc:{other_nmc}", "nmc", other_nmc) if other_nmc else
                      node(f"legacy:{r.id}", "legacy", r.legacy_code, cpse=code, description=r.description,
                           source=r.source, raw_id=r.id))
            if not other_nmc:
                edge(node(f"cpse:{code}", "cpse", code), target, "owns")
            edge(f"legacy:{mine}", target, "possible_duplicate" if p.status == "suggested" else "blocked",
                 pair_id=p.id, score=p.score, match_type=p.match_type, gate_failures=p.gate_failures)

    return {"center": center, "material": material_out(nm), "nodes": list(nodes.values()),
            "edges": list(edges.values())}
