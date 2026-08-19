-- Migration 0025 — corrective: the customer_id backfill 0022 could never run
--
-- WHY
-- ---
-- 0022_payment_links_customer_backfill_exhaustive.sql's Step 1 does:
--     UPDATE public.travel_leads l ... WHERE c.email = l.email
-- `travel_leads` has NEVER had an `email` column — only `phone` (added by
-- 0003). This statement raises `ERROR: 42703: column l.email does not exist`
-- and aborts the whole transaction. Verified against
-- `database/travel_schema.sql`'s `travel_leads` definition and every
-- `ADD COLUMN` across every migration file — none adds `email` to that table.
--
-- Found in a full-repo validation audit, 2026-08-15. 0022 is left completely
-- untouched (never edit an applied migration — fix forward instead).
--
-- WHAT THIS FILE ACTUALLY DOES
-- -----------------------------
-- Of 0022's five steps, only Step 2 (the phone-based backfill) was ever
-- genuinely new work:
--   - Step 1 (email match): broken as above, and was always redundant with
--     Step 2 anyway — GOGAGA_ANALYSIS_REPORT.md's own DB row already states
--     "phone is the lead's ONLY identity column" as the verified design,
--     which is exactly what makes an email-based match on `travel_leads`
--     architecturally wrong to have attempted, not just syntactically broken.
--   - Step 2 (phone match): correct, and — because Step 1 aborted before it
--     could run — has never actually executed anywhere, live or otherwise.
--     THIS is what this migration performs.
--   - Step 3 (payment_links.customer_id backfill from the linked lead):
--     already fully covered by 0021_traveller_access_paths.sql (identical
--     UPDATE, already applied) — not repeated here.
--   - Step 4 (index): already recovered under a new name in
--     0024_travel_leads_business_customer_index.sql — not repeated here.
--   - Step 5: informational only, nothing to repeat.
--
-- IMPORTANT — NOT YET APPLIED TO LIVE SUPABASE. This session has no
-- authenticated Supabase MCP access. Whether the live database's
-- `travel_leads` table matches this repo's schema (and therefore whether
-- this migration is even still needed there) is unverified — check
-- `information_schema.columns` for `travel_leads` on the live project before
-- applying, per the gogaga-migrations skill's second reality-check section.
--
-- Additive only: one UPDATE, NULL-guarded so it only touches rows that were
-- never backfilled, safe to run whether or not 0022 was ever attempted live.

UPDATE public.travel_leads l
SET customer_id = c.id
FROM public.travel_customer_profiles c
WHERE l.customer_id IS NULL
  AND l.business_id = c.business_id
  AND c.phone IS NOT NULL
  AND c.phone = l.phone
  AND NOT EXISTS (
    -- Avoid updating if multiple matches exist (ambiguity guard) — same
    -- pattern 0022 Step 2 used.
    SELECT 1 FROM public.travel_customer_profiles c2
    WHERE c2.business_id = l.business_id
      AND c2.phone = l.phone
      AND c2.id != c.id
  );

-- ============================================================
-- ROLLBACK
-- ============================================================
-- Non-destructive in isolation, but rolling back means re-orphaning any
-- travel_leads row this backfill linked to a customer profile.
--
-- UPDATE public.travel_leads SET customer_id = NULL
-- WHERE customer_id IN (
--     SELECT c.id FROM public.travel_customer_profiles c
--     -- (only if you can positively identify rows THIS migration set,
--     -- vs. ones already set some other way — do not run blindly)
-- );
