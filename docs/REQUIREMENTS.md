# EkCode — What you need

Everything required to run EkCode, and what is optional. For install steps see [SETUP.md](SETUP.md); for keys and external data see [API_KEYS_AND_SOURCES.md](API_KEYS_AND_SOURCES.md).

## 1. Machine

| | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4 cores (the 50k-rows-in-10-minutes target assumes 4 vCPU) |
| RAM | 8 GB | 16 GB (Docker, PyTorch and the embedding model together use about 3 GB) |
| Free disk | 10 GB | 20 GB (images, PostgreSQL data, model cache; about 5 GB more for the optional Ollama model) |
| OS | Windows 10/11, macOS or Linux | Any of these with Docker |
| Internet | Needed once, for the first build and the embedding model download | After that, EkCode runs fully offline with `LLM_PROVIDER=noop` |

## 2. Software

### Required

| Software | Version | Why |
|---|---|---|
| Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux) | Compose v2.20+ | Runs PostgreSQL, Redis, the API, the worker and the web server with one command |
| WSL 2 (Windows only) | — | Docker Desktop's backend on Windows; the background worker (RQ) also needs Linux |
| Git | any recent | To clone and version the project |

With Docker you do not need Python, Node or PostgreSQL on the host: they run inside containers.

### Only for local development outside Docker

| Software | Version | Why |
|---|---|---|
| Python | 3.11 or newer | Running the backend, tests and scripts on the host |
| Node.js | 22 LTS (20.19+ also works) | Running the React frontend with `npm run dev` |
| VS Code (or any editor) | — | Editing |

## 3. Containers that Compose starts

| Service | Image | Port on your machine |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` (PostgreSQL 16 + pgvector) | `127.0.0.1:5432` |
| `redis` | `redis:7-alpine` | `127.0.0.1:6379` |
| `api` | built from `backend/` (Python 3.11, FastAPI) | `127.0.0.1:8000` |
| `worker` | same image as `api` (RQ worker) | — |
| `web` | built from `frontend/` (Node 22 build, Nginx) | `8080` |
| `ollama` (optional, profile `llm`) | `ollama/ollama` | `127.0.0.1:11434` |

Ports 5432, 6379, 8000 and 8080 must be free. If you already run PostgreSQL locally, stop it or change the port in `docker-compose.yml`.

## 4. Python packages (installed automatically in the image)

From [backend/pyproject.toml](../backend/pyproject.toml):

| Area | Packages |
|---|---|
| Web API | fastapi, uvicorn, python-multipart, pydantic-settings, email-validator |
| Database | sqlalchemy 2, psycopg 3, pgvector |
| Security | pyjwt, argon2-cffi |
| Jobs | redis, rq |
| Files | pandas, openpyxl (xlsx), xlrd (xls), pdfplumber (UNSPSC PDF) |
| Matching / ML | torch (CPU build), sentence-transformers, rapidfuzz, lightgbm, scikit-learn, joblib, numpy |
| Other | pyyaml, httpx |
| Dev (tests, lint) | pytest, ruff |

## 5. Frontend packages

React 19, React Router 7, Vite 7, Tailwind CSS v4 (`@tailwindcss/vite`), Motion, TanStack Query, Recharts, React Flow (`@xyflow/react`), cmdk, sonner, react-dropzone, lucide-react, ESLint 9 and Playwright. They are listed in [frontend/package.json](../frontend/package.json) and installed with `npm install` or during the Docker build. For the end-to-end test, run `npx playwright install chromium` once.

## 6. Model and data

| Item | Required? | Notes |
|---|---|---|
| Embedding model `BAAI/bge-small-en-v1.5` | Yes | About 130 MB. Downloaded automatically from Hugging Face on the first upload, then cached in the `appdata` volume (`/data/hf`). No account or key needed. |
| Your CPSE material export (CSV/XLSX) | For real use | Needs at least a material code and a description column. Unit, group, price and quantity are optional. |
| Synthetic seed data | For demos | Generated locally by `scripts/generate_cpse_seed.py`; no download. |
| UNSPSC code list | Optional | Without it, every material gets category `9999` (Unclassified). |
| GST HSN master | Optional | Not needed in v1. |

## 7. Keys and accounts

None are required. EkCode runs completely with the defaults in `.env.example`. Optional keys (LLM providers, SAP sandbox) are explained in [API_KEYS_AND_SOURCES.md](API_KEYS_AND_SOURCES.md).
