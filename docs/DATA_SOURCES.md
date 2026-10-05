# EkCode — Data sources

Every dataset EkCode uses or can use: where it comes from, how it enters the system, and what to check before sharing it. **No real CPSE data ships with this repository.** How to download and import each item is in [API_KEYS_AND_SOURCES.md](API_KEYS_AND_SOURCES.md).

| Dataset | Origin | Enters EkCode via | Stored as | Required? |
|---|---|---|---|---|
| CPSE material master exports | Each CPSE's SAP/ERP (MM01/MM03 or SE16 exports) | Upload page or `POST /ingest/upload` | `raw_material`, `source='upload'` | For real use |
| SAP Product Master (OData) | The CPSE's S/4HANA (`API_PRODUCT_SRV`); the SAP API Hub sandbox for demos | Integrations → SAP pull | `raw_material`, `source='sap'` | Optional |
| Synthetic CPSE data | Generated locally by `scripts/generate_cpse_seed.py` | `scripts/load_seed.py` | `raw_material`, `source='synthetic'` | For demos |
| Sample files `test_upload_IOCL.csv`, `test_upload_ONGC.csv` | Hand-written for the UI testing guide | Upload page | `raw_material`, `source='upload'` | For the walkthrough |
| UNSPSC code list | unspsc.org | `scripts/import_unspsc_pdf.py` | `$DATA_DIR/reference/unspsc.csv` + `.npy` | Optional |
| GST HSN master | GST portal / CBIC | `scripts/import_hsn_excel.py` | `$DATA_DIR/reference/hsn.csv` | Optional |
| WDC Products benchmark | Web Data Commons (University of Mannheim) | `scripts/load_wdc_benchmark.py` | `$DATA_DIR/benchmarks/*.json` (report only) | Optional |
| Embedding model `BAAI/bge-small-en-v1.5` | Hugging Face | Downloaded on first use | `$DATA_DIR/hf` | Yes (automatic) |
| Abbreviation, noun and unit dictionaries | Written for EkCode (`backend/ekml/dictionaries/`) | Shipped; editable in Settings | YAML seed + `setting` table | Yes |

## Synthetic data (rule 5 of the build)

- **What:** about 250 catalogue items (bolts, stud bolts, nuts, spiral wound gaskets, gate and ball valves, seamless pipe, bearings, power cables and a few attribute-less items), spread over IOCL, ONGC, BPCL, HPCL, GAIL and NTPC.
- **How it is made realistic:** each CPSE file has its own header names, delimiter, code format, unit words, price level and writing habits (abbreviations, word order, inch vs NB, grade spellings, casing). Some items appear twice inside one CPSE.
- **Ground truth:** `truth.csv` gives the true item behind every row. `hard_negatives.csv` lists every pair of items that differ in exactly one critical attribute. The generator never drops the attribute that separates such a pair.
- **Labelling:** stored with `source='synthetic'` and shown with a *Synthetic* badge everywhere it appears (review cards, lists, detail pages, analytics). `load_seed.py --simulate-review` decisions are audited as `system` with the reason "simulated steward decision (ground truth)".
- **Prices and quantities** are generated from simple size-based formulas. They make the analytics pages meaningful for a demo, but they are not market prices.

## Real CPSE exports

- Data belongs to the CPSE. Upload only with permission, and keep the database on infrastructure the CPSE and the ministry approve.
- With `LLM_PROVIDER=noop` (default) or `ollama`, no material text leaves the server (ADR-12). Do not enable Gemini or Groq for real CPSE data.
- Uploaded files are kept under `$DATA_DIR/uploads` with random names. Delete them when they are no longer needed, or with `docker compose down -v`, which removes everything.

## Terms to check before redistribution

These are pointers, not legal advice. Confirm the current terms on each source's site.

| Source | Note |
|---|---|
| `BAAI/bge-small-en-v1.5` | Published by BAAI on Hugging Face; see the model card for its licence (MIT at the time of writing). |
| UNSPSC | The code set is managed by GS1 US; its download is subject to the UNSPSC terms of use. Do not republish the full list without checking them. |
| GST HSN master | Published by the Government of India for public use. |
| WDC Products | Research benchmark from Web Data Commons; cite it as the site asks and check its terms. |
| SAP API Business Hub sandbox | Demo data, for testing the integration only, under SAP's API Hub terms. |
| EkCode dictionaries and synthetic data | Created for this project. |
