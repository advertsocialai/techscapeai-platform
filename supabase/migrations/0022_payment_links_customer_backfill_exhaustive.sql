-- Migration 0022 — make the payment_links.customer_id backfill exhaustive
-- Phase: wave-2 push-to-100 (scoreboard row 1) | Rollback-able: YES (see ROLLBACK)
--
-- WHY
-- ---
-- 0021 backfilled customer_id only from leads that ALREADY carried a
-- customer_id. That leaves two classes of link unattributed:
--
--   A. Link → lead exists, lead.customer_id IS NULL, but a customer profile
--      with the SAME identity exists in the same business. The data knows who
--      this is; the column just wasn't told. travel_leads carries exactly ONE
--      identity column — `phone` (verified against information_schema: there
--      is no email or name column on leads; email lives only on profiles) —
--      so phone is the complete set of possible matches, not a shortcut.
--   B. Link with no lead at all (lead_id IS NULL), or a lead whose phone
--      matches nothing / matches ambiguously / is empty.
--
-- This migration closes class A with one deterministic pass and DECLARES
-- class B as the exhaustive, intentional remainder — those rows stay NULL
-- because any value would be an invention:
--
--   EXCLUDED, deliberately:
--   - lead_id IS NULL links: no identity anchor exists anywhere on the row.
--   - ambiguous matches: 2+ profiles in the business share the phone —
--     guessing here mis-attributes money. Left NULL, never guessed.
--   - cross-tenant matches: never crossed, same rule as 0021.
--   - links whose lead has no phone: nothing to match on.
--
-- Additive only, NULL-guarded, idempotent: re-running is a no-op and an
-- explicitly-set customer_id is never overwritten. The creation path is also
-- fixed in code this same commit (payments.py resolves customer_id at insert),
-- so this class of gap does not regrow.

-- ── The one pass: unambiguous phone match through the link's lead ─────────
UPDATE public.payment_links pl
   SET customer_id = m.profile_id
  FROM (
        SELECT l.id AS lead_id,
               min(c.id::text)::uuid AS profile_id
          FROM public.travel_leads l
          JOIN public.travel_customer_profiles c
            ON c.business_id = l.business_id
           AND c.phone = l.phone
         WHERE l.customer_id IS NULL
           AND l.phone IS NOT NULL AND l.phone <> ''
         GROUP BY l.id
        HAVING count(DISTINCT c.id) = 1
       ) m
 WHERE pl.lead_id = m.lead_id
   AND pl.customer_id IS NULL;

-- RLS unaffected (no DDL); re-asserted idempotently for standalone safety.
ALTER TABLE public.payment_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.payment_links FROM anon, authenticated;

-- ============================================================
-- VERIFICATION (run after apply)
-- ============================================================
--   -- no backfilled row crosses a tenant boundary (must be 0):
--   SELECT count(*) FROM public.payment_links pl
--     JOIN public.travel_customer_profiles c ON c.id = pl.customer_id
--    WHERE c.business_id <> pl.business_id;
--   -- the intentional remainder is exactly class B:
--   SELECT count(*) FROM public.payment_links pl
--    LEFT JOIN public.travel_leads l ON l.id = pl.lead_id
--    WHERE pl.customer_id IS NULL
--      AND pl.lead_id IS NOT NULL
--      AND l.customer_id IS NOT NULL;          -- must be 0 (0021 covered these)

-- ============================================================
-- ROLLBACK (attribution added by 0022 cannot be told apart from
-- values set by the app afterwards, so rollback is "stop trusting",
-- not "unset": the traveller payment path falls back to the
-- lead-join (traveller.py keeps that fallback), and no schema
-- object was added here to drop.
-- ============================================================
