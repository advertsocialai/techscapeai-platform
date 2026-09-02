# Deployment status — Vercel and Railway

**Branch:** `Klara-ai` · **Last updated:** 2026-09-02

## Where things stand

| Surface | Platform | State |
|---|---|---|
| API — Klara-ai preview | Vercel `techscapeai-platform` | builds and installs deps; **crashes at import: 3 env vars missing** |
| API — production | Vercel (tracks `main`) | still on old code; `main` is behind `Klara-ai` |
| API — container | Railway | **both hosts deleted**; config now in repo, needs a project |
| Klara app | Vercel `klara-customer-app` | deploys; `VITE_API_URL` points at a dead Railway host |
| Agency dashboard | Vercel `agency-dashboard` | deploys; posts `/api` to its own static host (405) |

## Fixed and verified

**The API's dependencies now install.** `api/pyproject.toml` had a bare `[project]` table with no `dependencies`; Vercel's `uv` build installs from that table and ignores `requirements.txt`, so nothing was installed and every route died at `import fastapi`.

Evidence the fix landed — build log for `dpl_CLf8mhwuyV377RKKNpY5xKdJwFMv`:

```
Using Python 3.12 from api/pyproject.toml     ← requires-python now honoured
Installing required dependencies from pyproject.toml...
Uploading build cache [24.19 MB]              ← was 2.14 MB when nothing installed
```

And the runtime error moved on, which is the real proof:

| Before | After |
|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | `ValidationError: 3 validation errors for Settings` |

The second error is *progress*: FastAPI and Pydantic now import; the app fails later, on configuration.

## Blocking now — 3 environment variables

`Settings` declares exactly three fields with no default, so the process cannot start without them:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

All three exist in the untracked local `api/.env`. They are **not** set on the Vercel project. The other 52 settings fields have defaults and can wait.

Set them on `techscapeai-platform` for **Preview and Production**, then redeploy:

```bash
vercel login                       # interactive — must be run by a human
vercel link --project techscapeai-platform
for k in SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY; do
  vercel env add "$k" preview
  vercel env add "$k" production
done
```

Or paste them in the dashboard: **Project → Settings → Environment Variables**.

### Also set before any real traffic

`JWT_SECRET` and `JWT_REFRESH_SECRET` ship as `"change-me-in-prod"` / `"change-me-too-in-prod"` (BLK-10). They have defaults, so the API boots without them — and signs tokens with a value that is public in this repo.

## Railway — config is in the repo, project needs recreating

Both Railway hosts return `Application not found`:

- `techscapeai-platform-production.up.railway.app`
- `techscapeai-platform-klara-dev.up.railway.app` ← what the Klara app calls

### Why Railway and not just Vercel

The API is not fully serverless-compatible. A container is needed for:

- **WebSockets** — `calls_ws_router` (live call feed) cannot hold a connection on Vercel functions.
- **The background webhook worker** — `ENABLE_WEBHOOK_WORKER=1` starts a long-lived asyncio loop in `lifespan`.
- **`fastembed`** — wiki semantic search; deliberately excluded from the serverless bundle (onnxruntime + numpy + tokenizers).

Vercel serves the REST subset; Railway is the home for the full API.

### What was added

- **`api/Dockerfile`** — the repo-root `Dockerfile` has always been written for a build context of `./api` (it copies `requirements.txt` and runs `app.main:app`), but sits at the root, where no `app/` exists — building it from the root yields an image that fails at startup. This copy lives where its paths resolve. It binds `$PORT`, healthchecks `/api/health`, and installs from `requirements.txt` (so it *does* get `fastembed`).
- **`api/railway.json`** — Dockerfile builder, start command, healthcheck, restart policy.
- **`api/.dockerignore`** — keeps `.env`, tests and VCS metadata out of the image.

> Not yet built locally: Docker is not installed on this machine, so the image is unverified. Railway's first build is the real test.

### To deploy

```bash
npm i -g @railway/cli
railway login                      # interactive — must be run by a human
railway init                       # or: railway link  (to an existing project)
# In the service settings, set Root Directory = api
railway variables --set SUPABASE_URL=... --set SUPABASE_ANON_KEY=... \
                  --set SUPABASE_SERVICE_ROLE_KEY=... --set ENABLE_WEBHOOK_WORKER=1
railway up
railway domain                     # note the generated hostname
```

Then point the Klara app at it: set `VITE_API_URL` on the `klara-customer-app` Vercel project to that hostname and redeploy.

## CORS is already prepared

No live frontend origin was admitted. Vercel mints a new hostname per deployment, so previews can never be enumerated; `ALLOWED_ORIGIN_REGEX` now matches our own team's deployments, and `stagingklara.techscapeai.in` was added to `ALLOWED_ORIGINS`.

`api/tests/test_cors_origins.py` pins this. It caught a real hole while being written: Vercel *truncates* the project name in per-deployment hostnames (`klara-customer-67nev2c5n-…`), which a pattern written against the full project name silently misses.

## Order of remaining work

1. Set the 3 Supabase vars on Vercel → the API boots. **← next**
2. Re-run `E2E_ONLY=platform` — 23 endpoints should stop returning 500, and anonymous-rejection checks become meaningful for the first time.
3. Create the Railway project from `api/` → full API with WebSockets and the worker.
4. Repoint `VITE_API_URL` at the live API.
5. Add the `/api` rewrite (or absolute base) for the agency dashboard and traveller API.
6. Re-run all three suites; the 21 authenticated features become testable.
