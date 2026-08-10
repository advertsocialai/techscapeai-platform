# Deploy readiness — code side (2026-08-10)

Everything deployable from code is in place. Exactly **two human dashboard
clicks** remain (BLK-4 / B-FE1-02 / B-FE1-03 — no Vercel API exposes Root
Directory, verified in PLATFORM_STATUS.md):

| Vercel project | Setting | Change |
|---|---|---|
| `agency-dashboard` | Root Directory | `agency-app` → **`agency-dashboard`** (the `agency-app` directory has never existed; every deploy dies at `build-container-init` with `NOW_SANDBOX_WORKER_ROOTDIR_NOT_EXIST`) |
| `techscapeai-platform` | Root Directory | *(empty)* → **`api`** |

Both under *Project Settings → Build & Deployment*. After each click, redeploy.

---

## 1. Frontends (customer-app, agency-dashboard)

- **SPA rewrite config**: `customer-app/vercel.json` already existed;
  `agency-dashboard/vercel.json` added 2026-08-10 (same `/(.*)` →
  `/index.html` rewrite). Without it, any deep link (`/mission-control`,
  `/onboarding/otp`) 404s on refresh because Vercel looks for a file, not a
  route.
- **Standalone builds verified 2026-08-10** (no install, existing lockfiles):
  - `customer-app`: `npm run build` → ✓ 146 modules, dist 377 kB JS
  - `agency-dashboard`: `npm run build` → ✓ 175 modules, dist 437 kB JS
- Vercel autodetects Vite (`framework: vite` needs no config): `npm ci` +
  `npm run build` + output `dist/` are all defaults once Root Directory is right.
- Known pre-existing CI-lint red (not deploy-blocking, Vercel does not lint):
  `customer-app/src/features/onboarding/pages/OtpPage.tsx:40` —
  `react-hooks` "setState synchronously within an effect" **error**.

## 2. FastAPI backend (Root Directory = `api`)

**Decision: `api/pyproject.toml` with `[tool.vercel] entrypoint = "app.main:app"`
— no `api/vercel.json`.**

Why this and not the alternatives:

- Vercel's FastAPI framework support auto-accepts an `app` variable only in a
  *default* entrypoint location (root `main.py`/`index.py`/`app.py`). Ours is
  `app/main.py` inside the `app` package — B-FE1-03 recorded Vercel's exact
  failure: *"No FastAPI entrypoint found ... found potential entrypoints:
  api/app/main.py"*, and Vercel's own suggested fix is the pyproject
  `entrypoint` key. `[tool.vercel] entrypoint` is the documented mechanism for
  non-default entrypoints (vercel.com/docs/frameworks/backend/fastapi, checked
  2026-08-10). With Root Directory=`api`, the module path is `app.main:app`
  (NOT `api.app.main:app` — `api/` has no `__init__.py` and must be the
  import root; verified below).
- A legacy `builds`/`routes` `vercel.json` also works but disables framework
  detection and the newer runtime features (incl. the WebSocket support
  `/ws/calls/{call_id}` needs), so it was rejected.
- A shim file (`api/main.py` re-exporting `app`) was rejected as a second
  entrypoint for humans to find and drift.
- Dependencies stay in `api/requirements.txt` (supported by the Vercel Python
  runtime; the pyproject deliberately has **no** `[project]` table so there is
  a single source of truth for packages).

**Verified locally 2026-08-10** (fixture env, `api/` as cwd):

- `python3 -m uvicorn app.main:app` boots clean; `GET /api/health` → 200
  `{"status":"healthy", ...}`; OpenAPI reports **163 paths**.
- Full test suite: **250 passed** (`pytest tests/ -q`).
- With `OBSERVABILITY_ALERTS=true` the alerting loop starts:
  `alerting: rule evaluation loop started (interval=5s, 3 rules)`.

**Env vars the Vercel project must define** (import-time-required, from
`app/core/config.py`): `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET` (all others
have defaults; see `.claude/skills/gogaga-backend/references/env-vars.md`).

**Known risk, flagged not fixed**: `fastembed==0.8.0` (wiki semantic search)
pulls onnxruntime + model tooling and may exceed Vercel's 250 MB uncompressed
function limit. It is lazy-imported (`services/travel/embeddings.py`) so it
cannot break *boot*, but if the **build** fails on bundle size the options are
(a) move embedding generation out-of-process, or (b) accept keyword-fallback
search on Vercel (the code already degrades to keyword search when the import
fails). Decide when the first real deploy attempt shows the actual size.

## 3. Uptime checks

`scripts/uptime_checks.yaml` defines the per-target probes (api `/api/health`
— NOT `/docs`/`/openapi.json`, which are DEBUG-only and 404 in production;
plus both SPA roots). URLs are `placeholder: true` until the two clicks above
produce real ones — flip them live by pasting the URL and deleting the flag.
`scripts/run_uptime_checks.py` executes the file (httpx): exit 0 verified on
pass, 1 on failure, skips placeholders loudly.

## 4. CI (`.github/workflows/ci.yml`)

Frontend matrix (lint/build/test/artifact, npm cache per app) + backend
(py_compile, import smoke, **unconditional gating pytest**, non-gating
coverage print, pip cache) + scoreboard check (Klara-ai) + docker (main).
YAML parse-validated. Actions billing itself is still BLK-5 — the workflow is
ready the moment runners return.
