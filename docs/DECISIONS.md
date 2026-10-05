# EkCode — Architecture Decision Records

This file records the decisions that shape EkCode. When a requirement is ambiguous, the ADRs below settle it. To change a decision, add a new ADR that supersedes the old one; do not edit history.

Each ADR follows **Context → Decision → Consequences**. ADR-01 to ADR-14 are the founding decisions. ADR-15 to ADR-20 write down rules that the PRD already implies, so they are not rediscovered during the build.

---

## Engineering rules

These apply to every change in the repository.

1. **Functional, not decorative.** Every button calls a real endpoint. Every number on screen is computed by the backend from the database. No hard-coded business arrays in React components, no `setTimeout` loaders, no lorem ipsum.
2. **JSX only on the front-end.** Files end in `.jsx` or `.js`. No TypeScript. Use JSDoc comments where types help.
3. **Tailwind CSS v4, CSS-first.** No `tailwind.config.js`. Tokens live in `frontend/src/index.css` under `@theme`. Use the `@tailwindcss/vite` plugin.
4. **One real pipeline.** Any real SAP/ERP export runs ingest → normalize → extract → embed → retrieve candidates → score with hard gates → review → approve → cluster → NMC → mapping export → audit.
5. **LLM optional.** Everything works with `LLM_PROVIDER=noop`.
6. **Accessibility is non-negotiable.** WCAG 2.2 AA in both themes, visible focus, keyboard reachable, reduced motion and reduced transparency honored.
7. **Latest stable libraries.** Never below React 19 or Tailwind v4. If a library API changed, adapt the code minimally.
8. **Quality gate after every phase.** `ruff`, `pytest`, `npm run lint` and `npm run build` must pass, and `docs/CHANGELOG.md` gets an entry.

## Index

| ADR | Decision | Status |
|---|---|---|
| [01](#adr-01--two-folders-one-compose) | Two folders, one Compose file | Accepted |
| [02](#adr-02--react--vite--jsx-not-nextjs) | React + Vite + JSX, not Next.js | Accepted |
| [03](#adr-03--tailwind-css-v4-css-first) | Tailwind CSS v4, CSS-first | Accepted |
| [04](#adr-04--motion-for-animation) | Motion for animation | Accepted |
| [05](#adr-05--postgresql--pgvector-as-the-only-store) | PostgreSQL + pgvector as the only store | Accepted |
| [06](#adr-06--local-embeddings-with-bge-small) | Local embeddings with bge-small | Accepted |
| [07](#adr-07--hybrid-matching-with-hard-gates) | Hybrid matching with hard gates | Accepted |
| [08](#adr-08--lightgbm-learned-scorer) | LightGBM learned scorer | Accepted |
| [09](#adr-09--rq-for-background-jobs-sse-for-progress) | RQ for background jobs, SSE for progress | Accepted |
| [10](#adr-10--cookie-based-jwt-auth-with-roles) | Cookie-based JWT auth with roles | Accepted |
| [11](#adr-11--semi-dumb-national-material-code) | Semi-dumb National Material Code | Accepted |
| [12](#adr-12--llm-off-by-default) | LLM off by default | Accepted |
| [13](#adr-13--docker-compose-not-kubernetes) | Docker Compose, not Kubernetes | Accepted |
| [14](#adr-14--append-only-audit-in-the-same-transaction) | Append-only audit in the same transaction | Accepted |
| [15](#adr-15--synthetic-data-is-labeled-and-uses-the-real-pipeline) | Synthetic data is labeled and uses the real pipeline | Accepted |
| [16](#adr-16--idempotent-ingestion) | Idempotent ingestion | Accepted |
| [17](#adr-17--versioned-same-origin-api) | Versioned, same-origin API | Accepted |
| [18](#adr-18--canonical-units) | Canonical units | Accepted |
| [19](#adr-19--auto-approval-is-opt-in) | Auto-approval is opt-in | Accepted |
| [20](#adr-20--deprecate-never-delete) | Deprecate, never delete | Accepted |

---

## ADR-01 — Two folders, one Compose

**Context.** EkCode has a Python back-end and a JavaScript front-end. Evaluators and new developers need to run the whole stack with one command.

**Decision.** Keep `backend/` and `frontend/` as sibling folders in one repository. `docker compose up --build` runs Postgres, Redis, the API, the worker and the web server. The API and the worker are built from the same backend image.

**Consequences.**
- One command brings up everything; one CI workflow covers both halves.
- Because API and worker share an image, ML code and dependencies cannot drift between them.
- CI needs both a Python and a Node toolchain.

## ADR-02 — React + Vite + JSX, not Next.js

**Context.** EkCode is an authenticated internal tool. It has no public pages and no SEO needs. The team prefers JSX over TypeScript.

**Decision.** Build a single-page app with React 19 and Vite, written in JSX. Nginx serves the static build and proxies `/api` to FastAPI.

**Consequences.**
- Fast dev loop and a plain static deploy; no Node server in production.
- No server rendering, so first paint depends on the JS bundle. Routes are code-split to meet LCP < 2.0 s.
- No compile-time types. JSDoc, ESLint and server-side validation at the API boundary fill the gap.
- Rejected: Next.js, whose SSR and server runtime add weight this tool does not need.

## ADR-03 — Tailwind CSS v4, CSS-first

**Context.** The UI needs a consistent, on-brand design system with dark and light themes, written in JSX.

**Decision.** Use Tailwind v4 through `@tailwindcss/vite`. Design tokens are defined under `@theme` in `src/index.css`; glass effects are `@utility` rules. There is no `tailwind.config.js`. Components are our own JSX in `src/components/ui/`, not a TSX UI kit.

**Consequences.**
- Tokens are CSS variables, so switching theme is a class change with no re-render of styles.
- We own accessibility for every primitive (focus rings, ARIA, keyboard behaviour).
- Glass surfaces must fall back to solid surfaces under `prefers-reduced-transparency`, and text on glass must still meet AA contrast.

## ADR-04 — Motion for animation

**Context.** Layout changes, list reordering in the review queue and page transitions need smooth, interruptible animation.

**Decision.** Use Motion (`motion/react`) for layout, presence and spring animations. The app root sets reduced motion to follow the user's OS preference, and custom animations check `useReducedMotion()`.

**Consequences.**
- One animation API across the app.
- With reduced motion on, animations become instant or opacity-only.
- Animation never stands in for data: no fake progress or loaders.

## ADR-05 — PostgreSQL + pgvector as the only store

**Context.** EkCode needs relational master data, vector similarity, fuzzy text matching and graph relationships, and every merge must commit atomically with its audit record.

**Decision.** PostgreSQL 16 with the `vector` (pgvector) and `pg_trgm` extensions is the single source of truth. Embeddings live in a 384-dimension vector column with an ANN index using cosine distance. Graph edges are ordinary relational rows, queried around one NMC at a time. Redis holds queue state only, never business data.

**Consequences.**
- One backup, one transaction boundary, no index sync drift.
- Comfortable for v1 volumes (hundreds of thousands to low millions of rows). Partitioning or a dedicated vector store is a v2 option.
- Deep multi-hop graph queries would be slower than in a graph database; the UI needs only one or two hops.
- Rejected: separate FAISS index (sync drift), Neo4j as primary store (second source of truth).

## ADR-06 — Local embeddings with bge-small

**Context.** Material descriptions are procurement data of government companies and should not leave the server. Embedding must run on ordinary CPU servers.

**Decision.** Use `BAAI/bge-small-en-v1.5` through sentence-transformers: 384 dimensions, CPU, normalized vectors.

**Consequences.**
- Free, offline and sovereign; small vectors keep the index compact.
- The first build downloads PyTorch and the model. Cache the model in a volume or image layer.
- English only. Hindi (v2) needs a multilingual model.
- Changing the model means re-embedding every row; treat it as a migration.

## ADR-07 — Hybrid matching with hard gates

**Context.** Embeddings think "M12 bolt" ≈ "M16 bolt", and lexical similarity thinks `SS304` ≈ `SS316`. In a national master, a wrong merge costs far more than a missed match.

**Decision.** Retrieve the top-15 candidates by pgvector ANN, compute six features (semantic, lexical, attribute, spec, unit, category) and score them. Deterministic hard gates compare extracted critical attributes (thread, length, nominal size, grade, pressure rating, schedule). If both sides state a value and the values conflict, the pair is `blocked` whatever its score.

**Consequences.**
- G2 is met by construction for every conflict the extractor can see, and the gates are unit-tested.
- Explanations come straight from features and gates, so every pair has green and red "why" chips.
- A missing value is not a conflict: it lowers the attribute feature. Gates are only as good as extraction, which is why a human still approves every merge.

## ADR-08 — LightGBM learned scorer

**Context.** Fixed weights cannot learn each CPSE's writing habits, but there are no labels on day one.

**Decision.** Start with a weighted formula over the six features, with weights in settings. Once stewards have made enough decisions, train a LightGBM classifier on the same features, store it in a model registry with its metrics, and let an admin activate it or roll back. Gates always run before the model.

**Consequences.**
- Small, CPU-fast models whose feature importances are easy to show.
- Retraining should refuse label sets that are too small or contain only one class.
- Rejected: TensorFlow plus PyTorch together. PyTorch is already needed by sentence-transformers, and two deep-learning frameworks would double image size for no gain.

## ADR-09 — RQ for background jobs, SSE for progress

**Context.** Ingesting 50k rows takes minutes, and the user must see live progress. Jobs: `ingest_job`, `retrain_job`, `webhook_job`, `sap_pull_job`.

**Decision.** Run jobs on Redis + RQ workers. Workers write stage and progress to the `ingest_job` row in PostgreSQL; the API streams that row to the browser over Server-Sent Events.

**Consequences.**
- Simple synchronous Python workers that reuse the same code as the API.
- Progress survives page reloads and API restarts because it lives in the database.
- Nginx must disable response buffering on the SSE route.
- RQ workers need `fork()`, so on Windows the worker runs in Docker or WSL, not natively.
- Rejected: Celery (heavier to operate), WebSockets (progress is one-way; SSE works over plain HTTP and reconnects on its own), FastAPI background tasks (die with the API process and have no retry).

## ADR-10 — Cookie-based JWT auth with roles

**Context.** Four roles (see PRD §6) with very different rights; machines also call the API.

**Decision.** Users log in to receive a JWT in an httpOnly, `SameSite=Lax` cookie, marked `Secure` in production. Passwords are hashed with argon2. Every route declares its allowed roles through a FastAPI dependency. Machine clients use API keys that are shown once and stored only as a hash.

**Consequences.**
- JavaScript never sees the token, so an XSS bug cannot steal it.
- `SameSite=Lax` keeps the cookie off cross-site POSTs; state-changing routes are never GET.
- API and SPA are same-origin (ADR-17), so production needs no CORS.
- Revocation without a session store: each token carries `pv`, a fingerprint of the user's password hash, checked on every request. Changing or resetting a password therefore invalidates every token issued before it.
- Nginx sends a Content-Security-Policy that forbids inline scripts. Never add an inline `<script>` to `index.html`; put it in `public/` (as `theme-init.js` is).

## ADR-11 — Semi-dumb National Material Code

**Context.** "Intelligent" codes that encode size or grade break the moment an attribute is corrected. Fully random codes give no sense of category.

**Decision.** The format is `NMC-CCCC-SSSSSS-K`: `CCCC` is a category prefix, `SSSSSS` a serial within the category, `K` a Luhn check digit. Attributes are stored in typed columns and never encoded in the code. Codes are never reused.

**Consequences.**
- Codes stay stable when descriptions or attributes are corrected.
- The check digit catches every single-digit typo and most swaps of adjacent digits before a lookup.
- The category prefix is fixed at issue time; reclassifying a material does not change its code.

## ADR-12 — LLM off by default

**Context.** An LLM can fill attributes that regex misses and polish descriptions, but it can also invent values, and cloud LLMs send data off-server.

**Decision.** `LLM_PROVIDER` is one of `noop` (default), `ollama`, `gemini`, `groq`. The LLM only fills attributes that extraction left empty and polishes standard descriptions. Every response is validated against the allowed attributes and value patterns, and anything invalid is dropped. The LLM never decides whether two materials match. `ollama` runs as an optional Compose service behind the `llm` profile.

**Consequences.**
- The pipeline is deterministic and offline by default.
- `ollama` is the on-prem production option.
- Cloud providers are allowed only for synthetic and benchmark data.

## ADR-13 — Docker Compose, not Kubernetes

**Context.** v1 runs on a single server or an evaluator's laptop.

**Decision.** Ship Docker Compose. A Helm chart is v2.

**Consequences.** Simple to run and debug; no horizontal autoscaling in v1.

## ADR-14 — Append-only audit in the same transaction

**Context.** G4 requires every change to be traceable, and an audit record must never exist without its change or the other way round.

**Decision.** `write_audit()` adds the audit row to the same database session as the change, so they commit or roll back together. Each row records actor (user, API key or system), action, entity, before and after JSON, reason and time. The application never updates or deletes audit rows.

**Consequences.**
- No change without audit, no audit without change.
- The table only grows; it is indexed for entity and time filters. Revoking UPDATE and DELETE at the database level is a hardening option.

## ADR-15 — Synthetic data is labeled and uses the real pipeline

**Context.** Demos and metrics need realistic data, but evaluators must be able to tell it from real CPSE uploads.

**Decision.** `generate_cpse_seed.py` writes messy CPSE-style files plus ground truth. `load_seed.py` feeds them through the same ingestion pipeline as a user upload. Those rows are stored with `source='synthetic'`, and the UI shows a "Synthetic" badge on them.

**Consequences.**
- G1 and G2 are measured on data that took the production path.
- Nobody can mistake demo data for real procurement data.

## ADR-16 — Idempotent ingestion

**Context.** CPSEs re-export their masters regularly, and uploads get retried.

**Decision.** Raw materials are unique on CPSE + legacy code. Upload upserts on that key.

**Consequences.**
- Uploading the same file twice never creates duplicates.
- A changed description in a re-upload updates the row, and the row is processed again.

## ADR-17 — Versioned, same-origin API

**Context.** Cookie auth works best without cross-origin requests, and external systems need a stable contract.

**Decision.** All endpoints live under `/api/v1`. The browser always calls a relative `/api` path: the Vite proxy forwards it in development, Nginx in production. OpenAPI docs are served at `/api/docs`.

**Consequences.**
- No CORS configuration in production.
- Breaking changes go to `/api/v2`.

## ADR-18 — Canonical units

**Context.** CPSEs write the same unit many ways (`NOS`, `EA`, `PCS`) and mix inches with millimetres.

**Decision.** Dimensions are stored in millimetres. Units of measure are stored as UN/ECE Rec 20 codes (for example `NOS`, `EA`, `PCS` → `C62`). The original text is kept next to the canonical value.

**Consequences.**
- Gates and features compare like with like.
- The original values stay available for display and audit.

## ADR-19 — Auto-approval is opt-in

**Context.** The product promise is that every AI suggestion goes through human approval, but exact duplicates can be very numerous.

**Decision.** Settings has an "auto-approve exact duplicates" switch, off by default. When an admin turns it on, only `EXACT_DUPLICATE` pairs above the auto threshold that passed every gate are approved automatically. They go through the same approve transaction, with actor `system` in the audit log.

**Consequences.**
- Human-in-the-loop by default.
- Every auto-approval is traceable and can be told apart from a steward's decision.

## ADR-20 — Deprecate, never delete

**Context.** ERPs and external systems may hold any NMC ever issued.

**Decision.** NMCs and mappings are never hard-deleted. A merged NMC becomes `deprecated`, points to its survivor through `successor_nmc`, and its legacy codes are remapped to the survivor. Resolving a legacy code or an old NMC follows the successor chain to the active code.

**Consequences.**
- Old codes keep resolving forever.
- Tables only grow, which is acceptable at master-data volumes.
