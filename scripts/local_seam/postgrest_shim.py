"""
LOCAL VERIFICATION SEAM — a minimal PostgREST-compatible shim. TEST INFRA ONLY.

Why this exists
---------------
The backend reaches its database exclusively through supabase-py, which speaks
PostgREST-over-HTTP — it never opens a direct Postgres connection. The sandbox
cannot reach supabase.co (BLK-3) and holds no service-role key (BLK-2), and the
real PostgREST server binary cannot be downloaded through the sandbox proxy
(403 on GitHub releases). This shim implements the SUBSET of the PostgREST
wire protocol that this codebase actually uses (measured by grep, see below),
backed by a local Postgres with the real migrations applied — so the UNMODIFIED
application code path (routers → services → supabase-py → HTTP → SQL) can be
exercised end-to-end against real rows.

What it deliberately is NOT
---------------------------
- Not a PostgREST replacement, not shipped, not imported by app code anywhere.
- Not an RLS test: it connects as the table owner, which mirrors service_role
  semantics (RLS bypass). RLS-as-anon remains proven against the live Supabase
  only (done earlier via MCP probes).
- Not a substitute for the real-Supabase path: it is an ADDITIONAL verification
  target (see PUSH-TO-100 wave-2 guardrails).

Covered operator surface (from `grep -rhoE '\\.(op)\\(' api/app`):
  eq neq gt gte lt lte like ilike is in or order limit range(offset)
  select (incl. ONE embedded resource, FK-inferred) insert update delete
  upsert (on_conflict) count=exact rpc
Anything outside this surface returns 400 loudly rather than guessing.

Run:  python scripts/local_seam/postgrest_shim.py  (listens on :54321)
Env:  SEAM_DSN (default postgresql://gogaga:gogaga_local@127.0.0.1:5432/gogaga_local)
"""
from __future__ import annotations

import datetime
import decimal
import json
import os
import re
import uuid

import psycopg
from fastapi import FastAPI, Request, Response
from psycopg import sql as pgsql

DSN = os.environ.get(
    "SEAM_DSN", "postgresql://gogaga:gogaga_local@127.0.0.1:5432/gogaga_local"
)

app = FastAPI(title="local-seam postgrest shim (TEST ONLY)")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# populated at startup: {(table, embedded_table): fk_column_on_table}
_FK: dict[tuple[str, str], tuple[str, str]] = {}


def _conn():
    return psycopg.connect(DSN, autocommit=True)


@app.on_event("startup")
def _load_fks() -> None:
    q = """
      SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table,
             ccu.column_name AS foreign_column
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
      JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
      WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
    """
    with _conn() as c, c.cursor() as cur:
        cur.execute(q)
        for tbl, col, ftbl, fcol in cur.fetchall():
            _FK[(tbl, ftbl)] = (col, fcol)


def _ident(name: str) -> pgsql.Identifier:
    if not _IDENT.match(name):
        raise ValueError(f"bad identifier: {name!r}")
    return pgsql.Identifier(name)


def _jsonable(v):
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, decimal.Decimal):
        # PostgREST serializes NUMERIC as a JSON number
        return float(v)
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


_OPS = {
    "eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
    "like": "LIKE", "ilike": "ILIKE",
}


def _one_filter(col: str, expr: str):
    """col + 'op.value' -> (sql_fragment, params)."""
    op, _, val = expr.partition(".")
    ident = _ident(col)
    if op in _OPS:
        return pgsql.SQL("{} {} %s").format(ident, pgsql.SQL(_OPS[op])), [val]
    if op == "is":
        if val == "null":
            return pgsql.SQL("{} IS NULL").format(ident), []
        if val in ("true", "false"):
            return pgsql.SQL("{} IS {}").format(ident, pgsql.SQL(val.upper())), []
        raise ValueError(f"unsupported is.{val}")
    if op == "in":
        inner = val.strip("()")
        items = [x.strip().strip('"') for x in inner.split(",") if x.strip() != ""]
        if not items:
            return pgsql.SQL("FALSE"), []
        ph = pgsql.SQL(", ").join(pgsql.SQL("%s") for _ in items)
        return pgsql.SQL("{} IN ({})").format(ident, ph), items
    raise ValueError(f"unsupported operator: {op!r}")


def _where(params) -> tuple[pgsql.Composable, list]:
    frags, binds = [], []
    for key, raw in params.multi_items():
        if key in ("select", "order", "limit", "offset", "on_conflict", "columns"):
            continue
        if key == "or":
            # or=(a.eq.1,b.is.null)  — postgrest-py sends the parenthesised list
            inner = raw.strip("()")
            sub, sub_binds = [], []
            for part in _split_top(inner):
                col, _, expr = part.partition(".")
                f, b = _one_filter(col, expr)
                sub.append(f)
                sub_binds.extend(b)
            frags.append(pgsql.SQL("({})").format(pgsql.SQL(" OR ").join(sub)))
            binds.extend(sub_binds)
            continue
        f, b = _one_filter(key, raw)
        frags.append(f)
        binds.extend(b)
    if not frags:
        return pgsql.SQL(""), []
    return pgsql.SQL(" WHERE ") + pgsql.SQL(" AND ").join(frags), binds


def _split_top(s: str) -> list[str]:
    """split on commas not inside parens (for or=(...) and select= lists)."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _parse_select(table: str, select: str):
    """Returns (plain_cols, embeds) where embeds = [(ftable, [fcols])]."""
    plain, embeds = [], []
    for part in _split_top(select or "*"):
        part = part.strip()
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)$", part)
        if m:
            embeds.append((m.group(1), [c.strip() for c in m.group(2).split(",")]))
        else:
            plain.append(part)
    return plain or ["*"], embeds


def _order(raw: str) -> pgsql.Composable:
    frags = []
    for part in raw.split(","):
        bits = part.split(".")
        col = _ident(bits[0])
        direction = pgsql.SQL("DESC") if "desc" in bits[1:] else pgsql.SQL("ASC")
        frags.append(pgsql.SQL("{} {}").format(col, direction))
    return pgsql.SQL(" ORDER BY ") + pgsql.SQL(", ").join(frags)


def _rows(cur) -> list[dict]:
    cols = [d.name for d in cur.description]
    return [{c: _jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def _err(e: Exception) -> Response:
    code = "23505" if "duplicate key" in str(e) else "P0001"
    status = 409 if code == "23505" else 400
    return Response(
        json.dumps({"message": str(e), "code": code}),
        status_code=status, media_type="application/json",
    )


@app.get("/rest/v1/{table}")
async def get_rows(table: str, request: Request):
    p = request.query_params
    plain, embeds = _parse_select(table, p.get("select", "*"))
    try:
        sel = pgsql.SQL(", ").join(
            pgsql.SQL("*") if c == "*" else _ident(c) for c in plain
        )
        q = pgsql.SQL("SELECT {} FROM {}").format(sel, _ident(table))
        where, binds = _where(p)
        q += where
        if p.get("order"):
            q += _order(p["order"])
        if p.get("limit"):
            q += pgsql.SQL(" LIMIT %s")
            binds.append(int(p["limit"]))
        if p.get("offset"):
            q += pgsql.SQL(" OFFSET %s")
            binds.append(int(p["offset"]))
        # .range() arrives as a Range header (postgrest-py: "0-9")
        rng = request.headers.get("range")
        if rng and re.match(r"^\d+-\d+$", rng) and not p.get("limit"):
            lo, hi = (int(x) for x in rng.split("-"))
            q += pgsql.SQL(" LIMIT %s OFFSET %s")
            binds.extend([hi - lo + 1, lo])
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, binds)
            rows = _rows(cur)
            # one-level embedded resources, FK-inferred (the codebase uses exactly one)
            for ftable, fcols in embeds:
                fk = _FK.get((table, ftable))
                if fk is None:
                    return Response(
                        json.dumps({"message": f"no FK {table}->{ftable}"}),
                        status_code=400, media_type="application/json")
                col_on_tbl, col_on_ftbl = fk
                for r in rows:
                    key = r.get(col_on_tbl)
                    if key is None:
                        r[ftable] = None
                        continue
                    fsel = pgsql.SQL(", ").join(_ident(x) for x in fcols)
                    cur.execute(
                        pgsql.SQL("SELECT {} FROM {} WHERE {} = %s").format(
                            fsel, _ident(ftable), _ident(col_on_ftbl)), [key])
                    frows = _rows(cur)
                    r[ftable] = frows[0] if frows else None
            headers = {}
            prefer = request.headers.get("prefer", "")
            if "count=exact" in prefer:
                cq = pgsql.SQL("SELECT count(*) FROM {}").format(_ident(table))
                w2, b2 = _where(p)
                cur.execute(cq + w2, b2)
                total = cur.fetchone()[0]
                headers["Content-Range"] = f"0-{max(len(rows) - 1, 0)}/{total}"
            return Response(json.dumps(rows), media_type="application/json",
                            headers=headers)
    except Exception as e:  # noqa: BLE001 — shim surfaces everything as PostgREST-ish errors
        return _err(e)


@app.post("/rest/v1/{table}")
async def insert_rows(table: str, request: Request):
    body = await request.json()
    rows = body if isinstance(body, list) else [body]
    prefer = request.headers.get("prefer", "")
    on_conflict = request.query_params.get("on_conflict")
    try:
        out = []
        with _conn() as c, c.cursor() as cur:
            for row in rows:
                cols = list(row.keys())
                idents = pgsql.SQL(", ").join(_ident(k) for k in cols)
                ph = pgsql.SQL(", ").join(pgsql.SQL("%s") for _ in cols)
                q = pgsql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    _ident(table), idents, ph)
                if "resolution=merge-duplicates" in prefer and on_conflict:
                    conflict_cols = pgsql.SQL(", ").join(
                        _ident(x) for x in on_conflict.split(","))
                    updates = pgsql.SQL(", ").join(
                        pgsql.SQL("{} = EXCLUDED.{}").format(_ident(k), _ident(k))
                        for k in cols)
                    q += pgsql.SQL(" ON CONFLICT ({}) DO UPDATE SET {}").format(
                        conflict_cols, updates)
                q += pgsql.SQL(" RETURNING *")
                vals = [json.dumps(v) if isinstance(v, (dict, list)) else v
                        for v in row.values()]
                cur.execute(q, vals)
                out.extend(_rows(cur))
        return Response(json.dumps(out), status_code=201,
                        media_type="application/json")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.patch("/rest/v1/{table}")
async def update_rows(table: str, request: Request):
    body = await request.json()
    try:
        sets = pgsql.SQL(", ").join(
            pgsql.SQL("{} = %s").format(_ident(k)) for k in body)
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v
                for v in body.values()]
        where, binds = _where(request.query_params)
        q = (pgsql.SQL("UPDATE {} SET ").format(_ident(table)) + sets
             + where + pgsql.SQL(" RETURNING *"))
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, vals + binds)
            return Response(json.dumps(_rows(cur)), media_type="application/json")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.delete("/rest/v1/{table}")
async def delete_rows(table: str, request: Request):
    try:
        where, binds = _where(request.query_params)
        q = (pgsql.SQL("DELETE FROM {}").format(_ident(table)) + where
             + pgsql.SQL(" RETURNING *"))
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, binds)
            return Response(json.dumps(_rows(cur)), media_type="application/json")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@app.post("/rest/v1/rpc/{fn}")
async def call_rpc(fn: str, request: Request):
    args = await request.json()
    try:
        keys = list(args.keys())
        kw = pgsql.SQL(", ").join(
            pgsql.SQL("{} := %s").format(_ident(k)) for k in keys)
        vals = [json.dumps(v) if isinstance(v, (dict, list)) else v
                for v in args.values()]
        q = pgsql.SQL("SELECT * FROM {}({})").format(_ident(fn), kw)
        with _conn() as c, c.cursor() as cur:
            cur.execute(q, vals)
            return Response(json.dumps(_rows(cur)), media_type="application/json")
    except Exception as e:  # noqa: BLE001
        return _err(e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=54321, log_level="warning")
