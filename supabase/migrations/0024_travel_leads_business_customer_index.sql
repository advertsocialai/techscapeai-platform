-- Migration 0024 — recover the index 0022 tried to add but silently didn't
--
-- WHY
-- ---
-- 0021_traveller_access_paths.sql already created an index NAMED
-- idx_travel_leads_customer on travel_leads(customer_id, business_id) —
-- customer-first, for the traveller read path (GET /me/payments and friends,
-- which filter by customer_id first).
--
-- 0022_payment_links_customer_backfill_exhaustive.sql later tried to create a
-- SECOND, differently-shaped index under the SAME name:
--   CREATE INDEX IF NOT EXISTS idx_travel_leads_customer
--       ON public.travel_leads(business_id, customer_id)
--       WHERE customer_id IS NOT NULL;
-- business-first, partial on customer_id IS NOT NULL — the shape that would
-- actually accelerate 0022's own verification query #2 (cross-tenant safety
-- check, scoped by business_id with customer_id IS NOT NULL) and any
-- per-business "how many leads are linked to a customer" reporting query.
--
-- Postgres's CREATE INDEX IF NOT EXISTS checks by NAME ONLY, not by
-- definition — so 0022's CREATE INDEX was a silent no-op the moment 0021 had
-- already run. The business_id-first partial index it intended was never
-- created. Found in a full-repo audit; 0022 itself is left untouched (never
-- edit an applied migration) — this file creates the missing index under its
-- own distinct name instead.
--
-- Additive only: one new index, no destructive ops, nothing renamed or
-- dropped. Safe to run whether or not 0022 has been (re-)applied anywhere.

CREATE INDEX IF NOT EXISTS idx_travel_leads_business_customer
    ON public.travel_leads (business_id, customer_id)
    WHERE customer_id IS NOT NULL;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Non-destructive: drops only the new index, no data loss.
--
-- DROP INDEX IF EXISTS public.idx_travel_leads_business_customer;
