"""
A hand-built fake of the tiny slice of the supabase-py surface this codebase
actually calls. Same philosophy as test_revenue_rollup_router_offline.py's
_DB/_Q, generalised so any router/service can run against it:

  * `FakeDB({"table_name": [rows...]})` seeds per-table rows.
  * Filters (.eq/.gte/.ilike/...) are accepted and IGNORED — a seeded table
    returns its rows regardless. Tests seed only what the endpoint should see.
  * .insert()/.upsert() echo the payload back (id/created_at defaulted) and
    record it in db.inserted[table] so tests can assert on writes.
  * .execute() returns an object with .data (and .count).

No network, no credentials, no supabase-py import. Install it by
monkeypatching app.database.connection.create_client — every client in the
app (get_supabase / get_supabase_admin / service singletons created after the
patch) funnels through that one factory.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


class FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        if count is None and isinstance(data, list):
            count = len(data)
        self.count = count


class FakeQuery:
    def __init__(self, rows, db=None, table=None):
        self._rows = [dict(r) for r in rows]
        self._db = db
        self._table = table
        self._single = False
        self._maybe_single = False

    # ── writes ────────────────────────────────────────────────────────
    def insert(self, payload, **_k):
        rows = payload if isinstance(payload, list) else [payload]
        out = []
        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            r = dict(r)
            r.setdefault("id", str(uuid.uuid4()))
            r.setdefault("created_at", now)
            r.setdefault("updated_at", now)
            out.append(r)
        if self._db is not None:
            self._db.inserted.setdefault(self._table, []).extend(out)
        self._rows = out
        return self

    def upsert(self, payload, **_k):
        return self.insert(payload)

    def update(self, payload, **_k):
        if self._rows:
            self._rows = [{**r, **payload} for r in self._rows]
        else:
            self._rows = [{"id": str(uuid.uuid4()), **payload}]
        if self._db is not None:
            self._db.updated.setdefault(self._table, []).append(dict(payload))
        return self

    def delete(self, **_k):
        return self

    # ── result-shape modifiers ────────────────────────────────────────
    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def execute(self):
        if self._single or self._maybe_single:
            return FakeResult(self._rows[0] if self._rows else None,
                              count=1 if self._rows else 0)
        return FakeResult(self._rows)

    # ── every filter/ordering method is an accepted no-op ─────────────
    def __getattr__(self, name):
        def _chain(*_a, **_k):
            return self
        return _chain


class FakeDB:
    def __init__(self, tables=None):
        self.tables = dict(tables or {})
        self.inserted: dict[str, list] = {}
        self.updated: dict[str, list] = {}
        self.tables_touched: list[str] = []

    def table(self, name):
        self.tables_touched.append(name)
        return FakeQuery(self.tables.get(name, []), db=self, table=name)

    # supabase-py alias
    def from_(self, name):
        return self.table(name)

    def rpc(self, name, params=None):
        self.tables_touched.append(f"rpc:{name}")
        return FakeQuery(self.tables.get(f"rpc:{name}", []), db=self,
                         table=f"rpc:{name}")


def install(monkeypatch, tables=None) -> FakeDB:
    """Route EVERY supabase client the app creates to one FakeDB."""
    from app.database import connection

    db = FakeDB(tables)
    monkeypatch.setattr(connection, "create_client", lambda url, key: db)
    monkeypatch.setattr(connection, "_supabase_client", None)
    return db
