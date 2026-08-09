-- Migration 0021 — make the traveller read paths correct and indexed
-- Phase: FE7 (traveller backend) | Rollback-able: YES (see ROLLBACK)
--
-- WHY
-- ---
-- The /travel/v1/me/* endpoints landed on the existing schema without any
-- migration, which was the right call — every join already existed. But
-- "the join exists" is not the same as "the join is supported". Checking the
-- actual indexes afterwards found three gaps that only a traveller query hits:
--
--   1. travel_bookings had NO index on customer_id. GET /me/trip filters on
--      (customer_id, business_id) and would sequentially scan every booking in
--      the platform to render one customer's trip.
--   2. travel_leads had NO index on customer_id. GET /me/payments starts there.
--   3. payment_links has no customer_id at all, so a traveller's links were
--      reachable only through their leads. A payment link raised against a
--      booking with no lead row was invisible to the person who has to pay it.
--
-- (3) is a data-model gap, not a performance one, and it is the one that
-- silently loses money: the customer simply never sees the request.
--
-- Additive only: two indexes, one nullable column, one backfill of rows that
-- currently have no other way to be attributed. Nothing is renamed or dropped,
-- and payment_links.lead_id keeps working exactly as before.

-- ── 1) Index the traveller's own booking lookup ───────────────────────────
-- Column order matches the query: equality on both, customer first because it
-- is the selective one — a business has many customers, a customer has few
-- bookings.
CREATE INDEX IF NOT EXISTS idx_travel_bookings_customer
    ON public.travel_bookings(customer_id, business_id);

-- ── 2) Index the lead->customer hop ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_travel_leads_customer
    ON public.travel_leads(customer_id, business_id);

-- ── 3) payment_links.customer_id — direct attribution ─────────────────────
-- NULLABLE on purpose. A link can legitimately exist before anyone knows which
-- customer profile it belongs to (raised against a bare lead, or a walk-in),
-- and forcing a value would either block those writes or invent an attribution.
-- ON DELETE SET NULL: deleting a customer profile must not destroy the record
-- that money was requested.
ALTER TABLE public.payment_links
    ADD COLUMN IF NOT EXISTS customer_id UUID
        REFERENCES public.travel_customer_profiles(id) ON DELETE SET NULL;

-- Backfill from the lead that already implies it. NULL-guarded, so re-running
-- is a no-op and an explicitly-set value is never overwritten.
UPDATE public.payment_links pl
   SET customer_id = l.customer_id
  FROM public.travel_leads l
 WHERE pl.lead_id = l.id
   AND pl.customer_id IS NULL
   AND l.customer_id IS NOT NULL
   -- Never cross a tenant boundary, even in a backfill. If these two ever
   -- disagree the row is left alone rather than silently re-attributed.
   AND pl.business_id = l.business_id;

CREATE INDEX IF NOT EXISTS idx_payment_links_customer
    ON public.payment_links(customer_id, business_id);

-- RLS on payment_links was enabled in 0010 and is unaffected by adding a
-- column; re-asserted idempotently so this file is safe standalone.
ALTER TABLE public.payment_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.payment_links FROM anon, authenticated;

-- ============================================================
-- VERIFICATION (run after apply)
-- ============================================================
--   -- indexes exist:
--   SELECT indexname FROM pg_indexes WHERE schemaname='public'
--    AND indexname IN ('idx_travel_bookings_customer','idx_travel_leads_customer',
--                      'idx_payment_links_customer');   -- expect 3
--   -- backfill crossed no tenant boundary (must be 0):
--   SELECT count(*) FROM public.payment_links pl
--     JOIN public.travel_customer_profiles c ON c.id = pl.customer_id
--    WHERE c.business_id <> pl.business_id;
--   -- the traveller trip lookup is index-backed, not a seq scan:
--   EXPLAIN SELECT * FROM public.travel_bookings
--    WHERE customer_id = '<uuid>' AND business_id = '<uuid>';

-- ============================================================
-- ROLLBACK (non-destructive — removes only what this file added.
-- Dropping customer_id loses the direct attribution, but lead_id
-- still holds the original indirect path.)
-- ============================================================
-- DROP INDEX IF EXISTS public.idx_payment_links_customer;
-- ALTER TABLE public.payment_links DROP COLUMN IF EXISTS customer_id;
-- DROP INDEX IF EXISTS public.idx_travel_leads_customer;
-- DROP INDEX IF EXISTS public.idx_travel_bookings_customer;
