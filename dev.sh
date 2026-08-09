#!/usr/bin/env bash
#
# Run the whole stack locally: backend + agency dashboard + customer app.
#
#   ./dev.sh          start everything
#   ./dev.sh backend  just the API
#   ./dev.sh stop     stop everything
#
# WITHOUT REAL SUPABASE CREDENTIALS this still runs, and that is deliberate —
# you can browse every screen's layout, routing and loading/error states. What
# you CANNOT do is log in or see data: /auth/login needs a real user row. Screens
# behind auth will show their error state. That is the missing database, not a
# broken build. Put real values in api/.env to make it all live.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/.dev-logs"
mkdir -p "$LOGS"

API_PORT=8000       # both vite proxies hardcode this — see vite.config.ts
DASH_PORT=5174
CUST_PORT=5175

red()  { printf '\033[31m%s\033[0m\n' "$*"; }
grn()  { printf '\033[32m%s\033[0m\n' "$*"; }
dim()  { printf '\033[2m%s\033[0m\n' "$*"; }

stop() {
  # Match on the exact command lines this script starts, so we never kill an
  # unrelated uvicorn/vite the developer is running for something else.
  pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $API_PORT" 2>/dev/null || true
  pkill -f "vite.*--port $DASH_PORT" 2>/dev/null || true
  pkill -f "vite.*--port $CUST_PORT" 2>/dev/null || true
  grn "stopped"
}

wait_for() {  # url, name, tries
  for _ in $(seq 1 "${3:-40}"); do
    if curl -sf -o /dev/null --max-time 2 "$1"; then return 0; fi
    sleep 0.5
  done
  return 1
}

start_backend() {
  cd "$ROOT/api"
  if [ -f .env ]; then
    dim "using api/.env"
    set -a; . ./.env; set +a
  else
    red "api/.env not found — starting with FIXTURE credentials."
    red "The API will run and every route will authenticate, but no data exists."
    dim "cp api/.env.example api/.env and fill it in to use a real database."
    export SUPABASE_URL="${SUPABASE_URL:-http://fixture.invalid}"
    export SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-fixture}"
    export SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-fixture}"
  fi
  # DEBUG on => /docs and /openapi.json are served. They are disabled otherwise.
  export DEBUG="${DEBUG:-true}"
  export JWT_SECRET="${JWT_SECRET:-dev-only-not-a-real-secret}"
  export JWT_REFRESH_SECRET="${JWT_REFRESH_SECRET:-dev-only-not-a-real-refresh}"

  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" \
    > "$LOGS/backend.log" 2>&1 &
  cd "$ROOT"
}

start_web() {  # dir, port, logname
  cd "$ROOT/$1"
  [ -d node_modules ] || { dim "installing deps in $1 (first run)"; npm install --silent; }
  nohup npm run dev -- --port "$2" > "$LOGS/$3.log" 2>&1 &
  cd "$ROOT"
}

case "${1:-all}" in
  stop) stop; exit 0 ;;
  backend) stop; start_backend ;;
  all)
    stop
    start_backend
    start_web agency-dashboard "$DASH_PORT" dashboard
    start_web customer-app     "$CUST_PORT" customer
    ;;
  *) red "usage: ./dev.sh [all|backend|stop]"; exit 1 ;;
esac

echo
# /openapi.json, not / — the API mounts everything under /api and the bare root
# is a legitimate 404. Health-checking / would report a working server as down.
if wait_for "http://127.0.0.1:$API_PORT/openapi.json" backend; then
  grn "  backend            http://localhost:$API_PORT/docs"
else
  red "  backend FAILED — see $LOGS/backend.log"; tail -5 "$LOGS/backend.log" || true
fi

if [ "${1:-all}" = "all" ]; then
  wait_for "http://127.0.0.1:$DASH_PORT/" dashboard \
    && grn "  agency dashboard   http://localhost:$DASH_PORT" \
    || red "  dashboard FAILED — see $LOGS/dashboard.log"
  wait_for "http://127.0.0.1:$CUST_PORT/" customer \
    && grn "  customer app       http://localhost:$CUST_PORT" \
    || red "  customer app FAILED — see $LOGS/customer.log"
fi

echo
dim "logs: $LOGS/   stop: ./dev.sh stop"
