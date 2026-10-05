# EkCode — How to start the project

Step-by-step, from a fresh laptop to the working web app with demo data. Check [REQUIREMENTS.md](REQUIREMENTS.md) first. Optional keys are in [API_KEYS_AND_SOURCES.md](API_KEYS_AND_SOURCES.md).

---

## 1. Install the tools (once)

### Windows 10/11

1. Enable WSL 2: open PowerShell **as Administrator** → `wsl --install` → restart.
2. Install Docker Desktop: https://www.docker.com/products/docker-desktop/. In Settings → General, keep "Use the WSL 2 based engine" on.
3. Give Docker enough memory: Settings → Resources, at least 6 GB.
4. Install Git: https://git-scm.com/download/win

### macOS

Install Docker Desktop (Apple Silicon or Intel build) and Git (`xcode-select --install`).

### Linux

Install Docker Engine and the Compose plugin (https://docs.docker.com/engine/install/), then add yourself to the `docker` group.

Check:
```bash
docker --version
docker compose version
```

## 2. Get the code and configure

```bash
cd ekcode                      # the project folder (contains docker-compose.yml)
cp .env.example .env           # Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and set at least:
- `JWT_SECRET`: 64 random characters, from `python -c "import secrets; print(secrets.token_hex(32))"`.
- `ADMIN_PASSWORD`: your own password.

If you copied this folder with its `.env`, a random `JWT_SECRET` is already there.

## 3. Start everything

```bash
docker compose up -d --build
```

- The first build downloads Python, CPU PyTorch, Node and the other packages, which takes 5–15 minutes. Later builds take seconds.
- The API creates tables, indexes, the nine CPSEs and the admin user on start (`python -m app.init_db`).

Check that it is running:
```bash
docker compose ps                                   # db, redis and api "healthy"; worker and web "running"
curl http://localhost:8000/api/v1/health            # {"ok":true}
```

- **Web app:** http://localhost:8080. Sign in with your `ADMIN_EMAIL` and `ADMIN_PASSWORD`.
- **API docs:** http://localhost:8000/api/docs

## 4. Try it with the two sample files

### In the web app

1. **Upload data**: choose CPSE `IOCL`, drop `test_upload_IOCL.csv`, check the auto-mapped columns, click **Start processing** and watch the stages. The first time takes a few minutes while the embedding model downloads.
2. Do the same with `test_upload_ONGC.csv` for `ONGC`.
3. **Review matches**: the M12 bolts, the 2" gate valves and the 4" gaskets are suggested. Press **A** to approve or **R** to reject; **J**/**K** move between pairs. The **Blocked by rule** tab shows M12 vs M16 and 150# vs 300#.
4. The approval toast shows the new national code. Open it from **National master**, then try **Knowledge graph**, **Find equivalent** (paste `SS HX BLT M12 L50`), **Analytics**, **Audit trail** and **Integrations → SAP mapping export**.

### Or through the API

In `/api/docs`, first `POST /api/v1/auth/login`, then:

1. `POST /api/v1/ingest/upload`: choose `test_upload_IOCL.csv`, set `cpse_code` = `IOCL`.
2. Copy `job.id` and `suggested_mapping` from the response.
3. `POST /api/v1/ingest/{job_id}/start` with body `{"mapping": <suggested_mapping>}`.
4. `GET /api/v1/ingest/{job_id}` until `status` is `done`. The first time takes a few minutes while the embedding model downloads.
5. Repeat with `test_upload_ONGC.csv` and `cpse_code` = `ONGC`.
6. `GET /api/v1/review/queue`: suggested pairs (M12 bolts, 2" gate valves, 4" gaskets).
   `GET /api/v1/review/queue?status=blocked`: hard negatives such as M12 vs M16 and 150# vs 300#.
7. Approve one: `POST /api/v1/review/{pair_id}/decision` with `{"decision": "approve"}`. The response has the new national code (`NMC-…`).

## 5. Load the demo data (optional)

Realistic, messy data for six CPSEs, stored as `source='synthetic'`:
```bash
docker compose exec api python scripts/generate_cpse_seed.py
docker compose exec api python scripts/load_seed.py --simulate-review 0.5 --promote-singletons
docker compose exec api python scripts/evaluate.py          # precision / recall / F1 vs. ground truth
```
Use `load_seed.py --queue` to let the worker process the files, so you can watch progress. Then run `--skip-ingest --simulate-review 0.5` once the jobs are done.

## 6. Run the checks

```bash
docker compose exec api ruff check .
docker compose exec api pytest -q
```
`test_api.py` adds a few rows, with random codes, to the database it runs against. Set `EKCODE_SKIP_PIPELINE=1` to skip the tests that need the embedding model.

Frontend (needs Node 22 on your machine):
```bash
cd frontend
npm install
npm run lint
npm run build
```

End-to-end test in a real browser, against the running stack on a **fresh** database:
```bash
cd frontend
npx playwright install chromium          # once
npm run test:e2e                         # E2E_BASE_URL defaults to http://localhost:8080
```

## 7. Frontend development with hot reload

Keep `db redis api worker` running in Docker, then:
```bash
cd frontend
npm install
npm run dev                             # http://localhost:5173, proxies /api to localhost:8000
```

## 8. Optional: local LLM

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```
Then set `LLM_PROVIDER=ollama` in `.env`, run `docker compose up -d api worker`, and turn on `use_llm` in Settings.

## 9. Everyday commands

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop (keeps data) | `docker compose stop` |
| Logs | `docker compose logs -f api` / `docker compose logs -f worker` |
| Rebuild after code changes | `docker compose up -d --build api worker` |
| Shell in the API container | `docker compose exec api bash` |
| Database shell | `docker compose exec db psql -U ekcode` |
| **Delete everything** (database, uploads, model cache) | `docker compose down -v` |

## 10. Running the backend without Docker (optional)

PostgreSQL and Redis still run in Docker; the API runs on your machine.
```bash
docker compose up -d db redis
cd backend
python -m venv .venv
.venv\Scripts\activate                   # macOS/Linux: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
set DATA_DIR=%CD%\data                   # PowerShell: $env:DATA_DIR="$PWD\data" ; macOS/Linux: export DATA_DIR=$PWD/data
python -m app.init_db
uvicorn app.main:app --reload --port 8000
```
Without a `backend/.env`, the defaults point at `localhost:5432` and `localhost:6379`, which suits this setup. The RQ **worker cannot run natively on Windows** (it needs `fork()`), so keep using `docker compose up -d worker` there.

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` (5432, 6379, 8000, 8080) | Stop the other program, or change the left-hand port in `docker-compose.yml` |
| `api` keeps restarting | `docker compose logs api`. Usually the database is not ready yet or `.env` has a typo. |
| Upload job stuck at `queued` | The worker is not running: `docker compose up -d worker`, then `docker compose logs worker`. After 30 minutes without progress the Upload page marks the job *stalled* and offers **Restart**. |
| Some rows "could not be split into columns" | Those lines have an extra delimiter (for example a `;` inside a description in a `;`-separated file). They are skipped and listed in the report; fix them in the file and upload again. |
| First upload very slow | The embedding model is downloading (one time, about 130 MB) |
| Upload rejected with 413 | The file is over 100 MB. Split it, or raise `MAX_UPLOAD_MB` in `.env` and `client_max_body_size` in `frontend/nginx.conf`. |
| Login returns 429 | Too many wrong passwords. Wait 15 minutes or restart the API. |
| Forgot admin password | Settings → Users (another admin), or `docker compose down -v` to start from an empty database |
| Docker on Windows is very slow | Keep the project inside the WSL filesystem, and give Docker more RAM and CPUs |
| `web` build fails at `npm run build` | Run `cd frontend && npm install && npm run build` on the host to see the full error, and paste it |
| Blank page or 502 at :8080 | The API is not up yet: `docker compose ps`, then `docker compose logs api` |
| `Permission denied` writing to `/data` | The data volume was created by an older root-run image: `docker compose down -v` once (this deletes the data) |
