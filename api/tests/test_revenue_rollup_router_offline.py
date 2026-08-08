"""
Offline proof of the ROUTER half of GET /analytics/revenue-rollup (Phase 4 T8).

The pure-function proofs live in test_fx_rollup_offline.py. This file proves
the wiring around it with a hand-built fake Supabase client: no database, no
network, no credentials. It exists because "the pure function is correct" and
"the endpoint calls it correctly" are two different claims.

Same scratchpad-location caveat as the other file — move to api/tests/ verbatim.
"""
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "/home/user/techscapeai-platform/api")

from fastapi import HTTPException  # noqa: E402

from app.routers.travel import usage as usage_router  # noqa: E402

UTC = timezone.utc
NOW = datetime.now(UTC)
BIZ = "b0000000-0000-0000-0000-0000000000b1"
BRANCH = "c0000000-0000-0000-0000-0000000000c1"
USER_IN_BRANCH = "d0000000-0000-0000-0000-0000000000d1"


# ── A fake supabase-py surface: only what the endpoint actually calls ──────
class _Q:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        return type("Res", (), {"data": self._rows})()


class _DB:
    def __init__(self, tables):
        self.tables = tables
        self.seen = []

    def table(self, name):
        self.seen.append(name)
        return _Q(self.tables.get(name, []))


def _payment(pid, amount, currency, days_ago, created_by=None):
    return {
        "id": pid, "amount": amount, "currency": currency,
        "created_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "created_by": created_by, "lead_id": None, "package_id": None,
        "gateway": "stub",
    }


SNAPSHOTS = [
    {"base_currency": "USD", "quote_currency": "INR", "rate": "83.00000000",
     "captured_at": (NOW - timedelta(days=20)).isoformat()},
]

PAID = [
    _payment("p-inr", "1000.00", "INR", 5, created_by=USER_IN_BRANCH),
    _payment("p-usd-ok", "10.00", "USD", 3, created_by=USER_IN_BRANCH),
    # 25 days ago — BEFORE the only USD snapshot (20 days ago). No rate exists.
    _payment("p-usd-gap", "500.00", "USD", 25, created_by=None),
]


def _install(monkeypatch, tables):
    db = _DB(tables)
    monkeypatch.setattr(usage_router, "get_supabase_admin", lambda: db)
    return db


def _manager(branch_id=None, role="manager"):
    return {"id": USER_IN_BRANCH, "business_id": BIZ, "role": role,
            "branch_id": branch_id}


def test_endpoint_totals_only_what_it_could_convert_and_says_so(monkeypatch):
    _install(monkeypatch, {"payment_links": PAID, "fx_rate_snapshots": SNAPSHOTS})
    out = usage_router.get_revenue_rollup(period="30d", branch=None, limit=5000,
                                          user=_manager())

    assert out["status_filter"] == "paid"
    assert out["quote_currency"] == "INR"
    # 1000 INR + 10 USD @ 83 = 1830.00 . The 500 USD row has no rate.
    assert out["total"] == "1830.00"
    assert out["complete"] is False
    assert out["total_is_partial"] is True
    assert out["rows_in"] == 3
    assert out["rows_converted"] == 2
    assert out["rows_unconvertible"] == 1
    assert [i["id"] for i in out["unconvertible"]["items"]] == ["p-usd-gap"]
    assert out["fx"]["live_rate_used"] is False
    assert out["fx"]["forward_fill"] is False
    print("\n  total=%s complete=%s unconvertible=%s"
          % (out["total"], out["complete"], out["unconvertible"]["items"]))


def test_branch_filter_reports_unattributable_rows_instead_of_hiding_them(monkeypatch):
    _install(monkeypatch, {
        "branches": [{"id": BRANCH}],
        "ts_users": [{"id": USER_IN_BRANCH}],
        "payment_links": PAID,
        "fx_rate_snapshots": SNAPSHOTS,
    })
    from uuid import UUID
    out = usage_router.get_revenue_rollup(
        period="30d", branch=UUID(BRANCH), limit=5000, user=_manager())

    ba = out["branch_attribution"]
    # p-usd-gap has created_by=None -> cannot be attributed to any branch.
    assert ba["excluded_unattributable_rows"] == 1
    assert ba["excluded_unattributable_ids"] == ["p-usd-gap"]
    assert out["rows_in"] == 2
    assert out["complete"] is True          # the two remaining rows both convert
    assert out["total"] == "1830.00"


def test_out_of_scope_branch_is_404_never_403(monkeypatch):
    _install(monkeypatch, {"branches": [], "payment_links": [], "fx_rate_snapshots": []})
    from uuid import UUID
    with pytest.raises(HTTPException) as err:
        usage_router.get_revenue_rollup(period="30d", branch=UUID(BRANCH),
                                        limit=5000, user=_manager())
    assert err.value.status_code == 404


def test_branch_pinned_manager_cannot_widen_scope(monkeypatch):
    db = _install(monkeypatch, {
        "branches": [{"id": BRANCH}],
        "ts_users": [{"id": USER_IN_BRANCH}],
        "payment_links": PAID,
        "fx_rate_snapshots": SNAPSHOTS,
    })
    out = usage_router.get_revenue_rollup(
        period="30d", branch=None, limit=5000, user=_manager(branch_id=BRANCH))
    # The caller asked for no branch; their own branch was forced on anyway.
    assert out["branch_id"] == BRANCH
    assert "ts_users" in db.seen


def test_bad_period_token_is_422(monkeypatch):
    _install(monkeypatch, {"payment_links": [], "fx_rate_snapshots": []})
    with pytest.raises(HTTPException) as err:
        usage_router.get_revenue_rollup(period="banana", branch=None,
                                        limit=5000, user=_manager())
    assert err.value.status_code == 422
