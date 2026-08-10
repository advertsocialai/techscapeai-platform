# Local verification seam — real rows through the real code path, no Supabase

**What this is:** the sandbox cannot reach supabase.co (BLK-3) and holds no
service-role key (BLK-2), so nothing had ever been proven against a real
database. This seam stands up a **local Postgres 16 + pgvector** with the
repo's real migrations, plus a **minimal PostgREST-compatible shim**
(`postgrest_shim.py`), so the **unmodified** application path — routers →
services → supabase-py → HTTP → SQL — runs against real rows.

**What it proved (2026-08-10, wave-2 run):**

| Evidence | How |
|---|---|
| All migrations apply on vanilla PG16 | `database/*.sql` + `supabase/migrations/0001–0021` → 38 tables, zero errors |
| Real signup | `POST /auth/register-business` → real `ts_businesses` + `ts_users` rows |
| Real login | `POST /auth/login` → JWT from a real user row |
| Dashboard writes+reads | lead, customer profile, booking created via the API |
| Traveller path end-to-end | request-otp → verify-otp → `/me/trip` returned the real booking |
| Cross-token separation live | traveller token on `/leads` → 401 against real data |
| **Postgres→screen (customer)** | Chromium drove `/trip/login` OTP flow in the real UI; TripPage rendered `SEAM-BALI-001` / Bali / agency name; 0 page errors |
| **Postgres→screen (dashboard)** | Real login in the real UI; Mission Control showed 1 lead / 1 booking; Journey Board rendered the lead card |

**What it deliberately does NOT prove** (still Supabase-blocked):
- RLS-as-anon against the managed stack (proven separately via MCP probes)
- service-role behaviors on real Supabase, PostgREST quirks beyond the shim's
  measured subset, Supabase-side performance

## Run it

```bash
# 1. Postgres (once): apt install postgresql-16 postgresql-16-pgvector
pg_ctlcluster 16 main start
sudo -u postgres psql -f scripts/local_seam/bootstrap.sql   # roles, db, auth stub
for f in database/schema.sql database/techscape_core_schema.sql \
         database/travel_schema.sql supabase/migrations/00*.sql; do
  sudo -u postgres psql -d gogaga_local -v ON_ERROR_STOP=1 -q -f "$f"
done

# 2. Shim (port 54321)
pip install "psycopg[binary]"
python scripts/local_seam/postgrest_shim.py &

# 3. API against it (fixture JWT-shaped keys — supabase-py checks the format)
cd api && DEBUG=true \
  SUPABASE_URL=http://127.0.0.1:54321 \
  SUPABASE_ANON_KEY=<any JWT-shaped string> \
  SUPABASE_SERVICE_ROLE_KEY=<same> \
  JWT_SECRET=local JWT_REFRESH_SECRET=local2 \
  python -m uvicorn app.main:app --port 8000
```

Frontends: customer-app with `VITE_API_URL`/`VITE_TRAVEL_API_URL` pointing at
the API; agency-dashboard proxies `/api` → `:8000` already (vite.config.ts).

Never deploy any part of this. The shim ignores auth headers by design — it
emulates the service-role (RLS-bypass) connection the backend uses.
