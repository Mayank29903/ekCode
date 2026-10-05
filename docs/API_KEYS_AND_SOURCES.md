# EkCode — Where to get API keys and data

**Nothing on this page is required.** With the defaults in `.env.example` (`LLM_PROVIDER=noop`, no SAP key), EkCode runs completely offline. Each section says what the item adds, where to get it, and which `.env` line it goes into.

After editing `.env`, restart the backend: `docker compose up -d api worker`.

> Never commit `.env`. It is already in `.gitignore`. Share keys with teammates privately.

---

## 1. JWT secret (set it; no external account)

The only value you should always change. It signs login sessions.

- Generate: `python -c "import secrets; print(secrets.token_hex(32))"` (or any 64 random characters)
- `.env`: `JWT_SECRET=<the value>`
- The `.env` in this repository already has a random one. With `COOKIE_SECURE=true` (production), the API refuses to start with a weak secret.

## 2. Admin login (no external account)

- `.env`: `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Change the password before anyone else can reach the server.
- These are used only the first time the database is created. To change them later, use Settings → Users, or delete the database volume (see SETUP.md).

---

## 3. LLM providers (optional)

The LLM only fills attributes the rules missed and polishes descriptions. It never decides a match, and every answer is validated (ADR-12). Choose one.

### Ollama: local, free, data stays on your machine (recommended for production)

- No key needed. Model runs in the `ollama` container.
- Start: `docker compose --profile llm up -d ollama`
- Download the model once (about 4.7 GB): `docker compose exec ollama ollama pull qwen2.5:7b-instruct`
- `.env`:
  ```
  LLM_PROVIDER=ollama
  OLLAMA_URL=http://ollama:11434
  OLLAMA_MODEL=qwen2.5:7b-instruct
  ```
- Needs about 8 GB of free RAM. Other models: https://ollama.com/library

### Google Gemini: cloud, free tier

- Get a key: sign in at https://aistudio.google.com → **Get API key** → **Create API key**.
- `.env`:
  ```
  LLM_PROVIDER=gemini
  GEMINI_API_KEY=<your key>
  GEMINI_MODEL=gemini-2.5-flash
  ```
- Check the current free "Flash" model name in AI Studio; names change over time.
- Sends descriptions to Google. Use only with synthetic or benchmark data (ADR-12).

### Groq: cloud, free tier, very fast

- Get a key: sign up at https://console.groq.com → **API Keys** → **Create API Key**.
- `.env`:
  ```
  LLM_PROVIDER=groq
  GROQ_API_KEY=<your key>
  GROQ_MODEL=llama-3.3-70b-versatile
  ```
- Check https://console.groq.com/docs/models for currently available models.
- Sends descriptions to Groq. Use only with synthetic or benchmark data.

Then enable it in the app: Settings → flags → **use_llm**, or `PUT /api/v1/admin/settings`.

---

## 4. SAP S/4HANA sandbox, Product Master API (optional, FR12)

Lets you pull materials live from SAP (`API_PRODUCT_SRV`) instead of uploading a file.

1. Create a free account at https://api.sap.com (SAP Business Accelerator Hub) and log in.
2. Search for **Product Master** (`API_PRODUCT_SRV`, SAP S/4HANA Cloud) and open it.
3. Click **Show API Key** and copy the key.
4. `.env`:
   ```
   SAP_BASE_URL=https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PRODUCT_SRV
   SAP_API_KEY=<your key>
   ```
5. Test: `POST /api/v1/integrations/sap/test` (or Integrations page → Test connection). Pull: `POST /api/v1/integrations/sap/pull` with `{"cpse_code": "IOCL", "top": 200}`.

The sandbox returns SAP demo products (not CPSE data), so it is good for demonstrating the integration. A real CPSE connection uses that CPSE's own S/4HANA URL and credentials, arranged with their SAP team.

## 5. data.gov.in (optional, reserved)

- Get a key: register at https://data.gov.in → sign in → **My Account** → generate API key.
- `.env`: `DATAGOVINDIA_API_KEY=<your key>`
- Reserved for public reference datasets; no feature uses it yet.

---

## 6. Reference data

### UNSPSC code list (optional, FR7 classification)

Gives each national code a real category prefix and UNSPSC suggestions. Without it the prefix is `9999`.

1. Download the UNSPSC codeset (English) from https://www.unspsc.org. Free registration may be required. The PDF, Excel or CSV version all work.
2. Put the file where the container can read it, for example `docker compose cp UNSPSC_English.xlsx api:/data/reference/`.
3. Import (also pre-computes the embeddings):
   `docker compose exec api python scripts/import_unspsc_pdf.py /data/reference/UNSPSC_English.xlsx`
4. Restart: `docker compose restart api worker`.

### GST HSN master (optional)

1. Download the HSN/SAC master Excel from the GST portal (https://www.gst.gov.in → Search HSN/SAC; the downloadable list is usually named `HSN_SAC.xlsx`), or from CBIC (https://www.cbic.gov.in).
2. `docker compose cp HSN_SAC.xlsx api:/data/reference/`
3. `docker compose exec api python scripts/import_hsn_excel.py /data/reference/HSN_SAC.xlsx`

### WDC Products benchmark (optional, independent accuracy check)

1. Download a test split (for example `wdcproducts80cc20rnd000un_test.json.gz`) from https://webdatacommons.org/largescaleproductcorpus/wdc-products/
2. `docker compose cp <file> api:/data/benchmarks/`
3. `docker compose exec api python scripts/load_wdc_benchmark.py /data/benchmarks/<file>`

### Embedding model (automatic)

`BAAI/bge-small-en-v1.5` from https://huggingface.co/BAAI/bge-small-en-v1.5. It downloads by itself on the first upload; no account or key is needed. To use another sentence-transformers model, set `EMBED_MODEL`. The vector size must stay 384, or the database column has to change.

---

## 7. Quick reference

| `.env` variable | Needed? | Where from |
|---|---|---|
| `JWT_SECRET` | Yes (change it) | Generate locally |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Yes (defaults work) | You choose |
| `DATABASE_URL`, `REDIS_URL`, `DATA_DIR` | Yes (defaults work with Docker) | — |
| `LLM_PROVIDER` + Ollama/Gemini/Groq settings | No | Sections 3 |
| `SAP_BASE_URL`, `SAP_API_KEY` | No | api.sap.com |
| `DATAGOVINDIA_API_KEY` | No | data.gov.in |
| `COOKIE_SECURE` | Set `true` behind HTTPS | — |
| `CORS_ORIGINS` | Defaults work | Add your frontend URL if it is not on port 5173 or 8080 |
