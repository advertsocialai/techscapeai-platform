# Backend testing — what "100%" on the scoreboard claims (and what it does not)

**100% =** the suite runs offline (`python -m pytest tests/ --cov=app`), all tests pass, AND every router module (45/45: 3 root + 17 techscape + 25 travel) is exercised through the real app via TestClient with **at least one 2xx success path and one 4xx failure path** (401 unauth for protected surfaces; validation/signature rejection for public webhooks), AND `core/deps.py` auth/RBAC branches are covered (≥90%, currently 92%), AND critical money logic (payment-link status machine + signed webhook) has behavior tests.

**Real measured line coverage: 54% overall** (was 43% at 80 tests; now 230 tests). The scoreboard number is NOT a line-coverage claim — lines in AI agents, report builders, and provider adapters that need live credentials remain uncovered by design (DB is faked via `tests/fake_supabase.py`; per-role RBAC/RLS against a real Supabase stays in gogaga-verifier's scripts).

Not claimed: no live-DB integration tests, no real telephony/payment-gateway calls, no coverage-in-CI gate yet.
