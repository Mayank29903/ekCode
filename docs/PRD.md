# EkCode — Product Requirements Document

**Product:** EkCode, an AI-driven National Unified Material Master for Indian CPSEs
**Context:** Smart India Hackathon 2026 · Ministry of Petroleum & Natural Gas (MoPNG)
**Version:** v1 · **Status:** in build
**Related docs:** [DECISIONS.md](DECISIONS.md) (architecture decisions) · [FLOW.md](FLOW.md) (pipelines, transactions, states) · [CHANGELOG.md](CHANGELOG.md)

---

## 1. Problem

CPSEs in Oil & Gas, Power, Steel, Mining and Heavy Engineering buy and stock similar materials, but each keeps its own SAP/ERP material master. The same physical item carries different codes, descriptions, units and classes:

| CPSE | Legacy code | Description |
|---|---|---|
| IOCL | 10045872 | HEX BOLT M12X50 SS304 |
| ONGC | 3000211 | Bolt hexagonal SS 12x50mm |
| BPCL | MT-88213 | SS HX BLT M12 L50 |

Result: duplicate inventory, fragmented spend, no demand aggregation, slow specification finalization.

## 2. Solution

**EkCode** detects identical, near-duplicate and functionally equivalent materials across CPSEs, proposes a standardized noun-modifier description and a **Common National Material Code (NMC)**, keeps full traceability to every legacy code, routes every AI suggestion through human approval, learns from every decision, and integrates back into SAP.

**Worked example (the three rows above).** EkCode normalizes `HX BLT` to `hexagonal bolt` and reads `12x50mm` on a bolt as thread M12 and length 50 mm, extracts attributes, and suggests the rows as matches. ONGC and BPCL both write `SS` without a grade, so those pairs go to a steward instead of being treated as exact duplicates. Once the steward approves them, one NMC is issued (for example `NMC-CCCC-000123-K`) with the standard description `BOLT; THREAD: M12; LENGTH: 50 MM; MATERIAL: SS304`, and 10045872, 3000211 and MT-88213 all map to it. An `M16` bolt would never join this cluster, because a hard gate blocks it.

## 3. Product principles

1. **Functional, not decorative.** Every number on screen is computed by the backend from the database. No mock data, no hard-coded business arrays, no fake loaders.
2. **Human in the loop.** The AI suggests and a data steward decides. Every decision is audited and becomes a training label.
3. **Precision before recall when merging.** A missed duplicate costs one extra review; a wrong merge corrupts the national master. Hard gates and human approval stand between every suggestion and a merge.
4. **Sovereign by default.** The platform runs fully offline with `LLM_PROVIDER=noop` and local embeddings.
5. **Honest data.** Synthetic seed rows are stored with `source='synthetic'` and carry a "Synthetic" badge wherever they appear.
6. **Accessible and keyboard-first.** WCAG 2.2 AA in both themes; the review queue can be worked through without a mouse.

## 4. Goals and success metrics

| # | Goal | Target |
|---|---|---|
| G1 | Find duplicates/equivalents across CPSEs | Pairwise F1 ≥ 0.90 on seeded ground truth |
| G2 | Never merge different materials | Precision ≥ 0.97 for suggestions above auto threshold; 100% of seeded hard negatives (M12 vs M16, 150# vs 300#, SS304 vs SS316) blocked |
| G3 | Standardize | Every active NMC has a noun-modifier description + typed attributes |
| G4 | Traceability | Every legacy code maps to at most one active NMC; every change audited |
| G5 | Review speed | A steward decides a pair in under 10 seconds using only the keyboard |
| G6 | ERP integration | Import SAP export, export SAP-loadable mapping, live pull from SAP OData sandbox |

G1 and G2 are measured by `backend/scripts/evaluate.py` against the ground truth written by `backend/scripts/generate_cpse_seed.py`, after the seed files have gone through the real ingestion pipeline.

## 5. Non-goals for v1

Replacing ERPs, price negotiation, vendor onboarding, non-English descriptions (design data model for Hindi in v2).

## 6. Roles

| Role | Can |
|---|---|
| `admin` | Everything, users, thresholds, dictionary, models |
| `data_steward` | Review, approve, reject, merge, edit descriptions, issue codes |
| `cpse_user` | Upload for own CPSE, browse, search, export own mapping |
| `auditor` | Read-only everything including audit log |

Roles are enforced on the server for every route. The UI hides actions a role cannot perform, but hiding is a convenience, not the control.

## 7. Functional requirements

- **FR1 Ingestion:** CSV/XLSX upload; automatic fuzzy column mapping to SAP fields `MATNR, MAKTX, LONG_TEXT, MEINS, MATKL, PRICE, QTY`; preview; validation report; idempotent re-upload (upsert on `cpse + legacy_code`); async job with live progress over Server-Sent Events.
- **FR2 Normalization:** lowercase, punctuation, abbreviation expansion (editable dictionary), inch → mm, UoM → UN/ECE Rec 20 codes.
- **FR3 Attribute extraction:** noun, thread, length, nominal size, grade, pressure rating, schedule, standard; regex first, optional LLM fill; confidence per attribute.
- **FR4 Matching:** pgvector ANN candidate retrieval; hybrid features (semantic, lexical, attribute, spec, unit, category); hard conflict gates; classification into `EXACT_DUPLICATE | NEAR_DUPLICATE | FUNCTIONAL_EQUIVALENT | DIFFERENT`; human-readable explanation for every pair.
- **FR5 Review workflow:** queue sorted by impact (spend × uncertainty); side-by-side diff; approve/reject with keyboard; bulk actions; "blocked by hard gate" tab; optimistic UI.
- **FR6 Clustering & NMC:** approval merges clusters (with conflict check); NMC issued with category prefix + serial + Luhn check digit; deprecated codes point to successors; "Issue codes for unique materials" for singletons.
- **FR7 Classification:** UNSPSC suggestion from the imported codeset (embedding nearest neighbor), HSN optional.
- **FR8 Search:** paste any description → ranked national materials and unmapped legacy items with "why" chips.
- **FR9 Analytics:** KPIs, duplicates by CPSE, categories, match-type mix, aggregation opportunities (same NMC bought by ≥2 CPSEs with combined annual value).
- **FR10 Knowledge graph:** NMC ↔ legacy codes ↔ CPSEs ↔ standard ↔ category, interactive.
- **FR11 Audit:** append-only log, before/after JSON, actor, reason, filterable UI.
- **FR12 Integration:** SAP-format mapping export per CPSE; SAP OData (API_PRODUCT_SRV) pull; API keys; HMAC-signed webhooks on NMC events.
- **FR13 Continuous learning:** decisions become labels; LightGBM retrain; model registry with metrics; activate/rollback.
- **FR14 Settings:** threshold sliders, auto-approve exact duplicates toggle, dictionary editor, user management.

### 7.1 Match types

Every scored pair gets exactly one type. The examples are illustrative; the actual type comes from the score thresholds in Settings, after the hard gates have run.

| Type | Meaning | Example |
|---|---|---|
| `EXACT_DUPLICATE` | Same material and specification; normalized descriptions and every stated attribute agree. | `HEX BOLT M12X50 SS304` vs `HEX BOLT M12 X 50 SS304` |
| `NEAR_DUPLICATE` | Same material and specification, written differently (abbreviations, word order, units, typos). | `HEX BOLT M12X50 SS304` vs `BOLT HEX SS 304 M12 L=50MM` |
| `FUNCTIONAL_EQUIVALENT` | Interchangeable for the same duty, but a non-critical attribute is unstated or expressed differently (for example a different standard reference). Needs steward judgement. | `HEX BOLT M12X50 SS304` vs `Bolt hexagonal SS 12x50mm` |
| `DIFFERENT` | Not the same material. Never merged. Every pair blocked by a hard gate is `DIFFERENT`. | `M12` vs `M16` bolt · `150#` vs `300#` flange · `SS304` vs `SS316` |

A hard gate fires only when **both** sides state a value for a critical attribute and the values conflict. A missing value is not a conflict: it lowers the attribute-agreement feature and is shown to the steward in the diff.

### 7.2 Review impact

The review queue is ordered by impact, so stewards spend their time where the money is: **impact = combined annual spend of the pair (price × quantity of both legacy items) × model uncertainty**. Uncertainty is highest for scores near the decision boundary. The exact formula lives in `backend/app/services/match_service.py`.

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| API latency | p95 < 300 ms for non-batch APIs |
| Throughput | 50k rows end-to-end < 10 min on 4 vCPU |
| Front-end performance | LCP < 2.0 s; Lighthouse ≥ 90 for performance, accessibility and best practices |
| Responsive | Works at 360 px width |
| Themes | Dark and light, WCAG 2.2 AA contrast in both |
| Accessibility | Visible focus, every control keyboard reachable, `prefers-reduced-motion` and `prefers-reduced-transparency` honored |
| Security | OWASP ASVS Level 1 |
| Data sovereignty | No data leaves the server when `LLM_PROVIDER` is `noop` or `ollama` |

## 9. Requirement traceability

Where each requirement is implemented. Paths are relative to the project root.

| FR | Backend | ML (`backend/ekml/`) | Frontend (`frontend/src/`) |
|---|---|---|---|
| FR1 Ingestion | `routers/ingest.py`, `services/ingest_service.py`, `workers/jobs.py` | — | `pages/Ingest.jsx`, `components/ingest/*`, `hooks/useJobStream.js` |
| FR2 Normalization | `settings_store.py` (dictionary) | `normalize.py`, `dictionaries/*.yaml` | `pages/Settings.jsx` (dictionary editor) |
| FR3 Extraction | — | `extract.py`, `llm.py` | `pages/MaterialDetail.jsx` |
| FR4 Matching | `services/match_service.py` | `embed.py`, `features.py`, `gates.py`, `score.py`, `explain.py` | `components/review/*` |
| FR5 Review | `routers/review.py`, `services/cluster_service.py` | — | `pages/Review.jsx`, `hooks/useHotkeys.js` |
| FR6 Clustering & NMC | `services/cluster_service.py`, `services/nmc_service.py` | `nmc.py`, `standardize.py` | `pages/Review.jsx`, `pages/Materials.jsx` |
| FR7 Classification | `scripts/import_unspsc_pdf.py`, `scripts/import_hsn_excel.py` | `taxonomy.py` | `pages/MaterialDetail.jsx` |
| FR8 Search | `routers/search.py` | `embed.py`, `explain.py` | `pages/Search.jsx` |
| FR9 Analytics | `routers/analytics.py` | — | `pages/Dashboard.jsx`, `pages/Analytics.jsx`, `components/dashboard/*` |
| FR10 Knowledge graph | `routers/graph.py` | — | `pages/Graph.jsx` |
| FR11 Audit | `audit.py`, `routers/audit_log.py` | — | `pages/Audit.jsx` |
| FR12 Integration | `routers/integrations.py`, `services/sap_service.py`, `services/webhook_service.py` | — | `pages/Integrations.jsx` |
| FR13 Continuous learning | `routers/admin.py`, `workers/jobs.py` | `train.py`, `score.py` | `pages/Settings.jsx` |
| FR14 Settings | `routers/admin.py`, `settings_store.py` | — | `pages/Settings.jsx` |

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Two different materials get merged (M12 vs M16, 150# vs 300#) | Deterministic hard gates run before any score; human approval; merges re-check gates on the canonical attributes of both NMCs; deprecated codes are kept with a successor pointer, so every merge stays traceable. |
| Extraction misses a critical attribute, so a gate cannot fire | Missing values lower the score instead of counting as agreement; the steward sees unstated attributes in the diff; the abbreviation dictionary is editable in Settings. |
| Cold start: no steward decisions to learn from | Weighted formula until enough labels exist; LightGBM models go through a registry with metrics and rollback. |
| LLM invents attributes | LLM is optional (`noop` by default), only fills gaps the regex left, every output is validated, and the LLM never decides a match. |
| Material data leaves the country | Local embeddings; `ollama` for on-prem LLM; cloud LLM providers are limited to synthetic and benchmark data. |
| Slow first start (PyTorch and embedding model download) | Model cached in a Docker volume or image layer; documented in the README. |
| Large uploads block the API | Parsing, embedding and matching run in an RQ worker; progress streams over SSE. |

## 11. Glossary

| Term | Meaning |
|---|---|
| CPSE | Central Public Sector Enterprise (for example IOCL, ONGC, BPCL). |
| Legacy code | A CPSE's own material number in its ERP (SAP `MATNR`). |
| NMC | National Material Code, the common code EkCode issues: `NMC-CCCC-SSSSSS-K` (category prefix, serial, Luhn check digit). |
| Cluster | The set of legacy materials approved as the same material. A cluster maps to one active NMC. |
| Singleton | A legacy material with no approved match. It can still receive its own NMC. |
| Noun-modifier description | Standard naming that puts the class noun first, then its modifier, then attributes in a fixed order, e.g. `VALVE, GATE; SIZE: 2 IN; RATING: 150#; MATERIAL: A105`. |
| Hard gate | A deterministic rule that blocks a pair when both sides state conflicting critical attributes (thread, size, pressure rating, schedule, grade). |
| Data steward | The person who approves or rejects suggested matches. |
| `MATNR` · `MAKTX` · `LONG_TEXT` · `MEINS` · `MATKL` | SAP material number · short description · long text · base unit of measure · material group. |
| UN/ECE Rec 20 | International codes for units of measure (for example `C62` for a count of one, `MTR` metre, `KGM` kilogram). |
| UNSPSC | United Nations Standard Products and Services Code, an 8-digit product classification. |
| HSN | Harmonized System of Nomenclature, the product codes used for Indian GST. |
| ANN | Approximate nearest-neighbour search, done in PostgreSQL by pgvector. |
| SSE | Server-Sent Events, a one-way HTTP stream used for live job progress. |

## 12. Later versions (v2 and beyond)

- Hindi and other Indian-language descriptions, using a multilingual embedding model.
- Helm chart and Kubernetes deployment (v1 ships Docker Compose, see ADR-13).
- A cross-encoder re-ranker on top of the LightGBM scorer.
- Single sign-on against the ministry's identity provider.
- Monthly partitioning of the audit log.
