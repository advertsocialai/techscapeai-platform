-- Migration 0020 — fix the tenant-B fixture's unusable email addresses
-- Phase: 5 | Rollback-able: YES (see ROLLBACK — restores the old addresses)
--
-- WHAT WAS WRONG
-- --------------
-- 0018 seeded the isolation fixture with `@regression-fixture-tenant-b.test`
-- addresses. `.test` is an RFC 2606 special-use TLD, and the backend's own
-- validator refuses it — `LoginIn.email` is a Pydantic `EmailStr`, and
-- email-validator rejects special-use names outright:
--
--   POST /auth/login {"email": "owner@regression-fixture-tenant-b.test", ...}
--   422 -> "value is not a valid email address: The part after the @-sign is
--           a special-use or reserved name that cannot be used with email"
--
-- So all four fixture accounts were unable to authenticate BY CONSTRUCTION.
-- The fixture exists for exactly one purpose — making the 4-role x 2-tenant
-- access matrix and the cross-tenant isolation assertions runnable — and it
-- could not clear step one of any of them. Nothing caught it because the
-- fixture had never been applied, let alone logged into.
--
-- WHY example.com AND NOT .example / .invalid / .localhost
-- --------------------------------------------------------
-- Verified against the real validator rather than guessed:
--     .test        rejected      .example      ACCEPTED
--     .invalid     rejected      .example.com  ACCEPTED
--     .localhost   rejected
-- `.example` happens to pass today, but only because it is absent from
-- email-validator's special-use list — the same list that already blocks its
-- three RFC 2606 siblings. Depending on that gap would put this fixture one
-- library update away from breaking again, in precisely the same way.
--
-- `example.com` is IANA-reserved for documentation (RFC 2606 §3), so it can
-- never be a deliverable mailbox — the safety property `.test` was chosen for
-- is fully retained — while being an ordinary registered domain that no
-- validator special-cases. Robust for the right reason, not by luck.
--
-- The `regression-fixture-tenant-b` marker is preserved in every address, so
-- cleanup_test_artifacts.py still finds every row by one string.
--
-- Additive/UPDATE-only: touches ONLY the five fixture rows created by 0018,
-- all matched by their fixed UUIDs. No schema change, no other tenant.

-- ── 1) The four login accounts ─────────────────────────────────────────────
UPDATE public.ts_users
   SET email = replace(email,
                       '@regression-fixture-tenant-b.test',
                       '@regression-fixture-tenant-b.example.com')
 WHERE business_id = '00000000-0000-4000-b000-00000000000b'
   AND email LIKE '%@regression-fixture-tenant-b.test';

-- ── 2) The business contact address ────────────────────────────────────────
-- Same defect, same fix: any endpoint validating contact_email as an EmailStr
-- would reject this tenant.
UPDATE public.ts_businesses
   SET contact_email = replace(contact_email,
                               '@regression-fixture-tenant-b.test',
                               '@regression-fixture-tenant-b.example.com')
 WHERE id = '00000000-0000-4000-b000-00000000000b'
   AND contact_email LIKE '%@regression-fixture-tenant-b.test';

-- ============================================================
-- VERIFICATION (run after apply)
-- ============================================================
--   SELECT email, role FROM public.ts_users
--    WHERE business_id = '00000000-0000-4000-b000-00000000000b' ORDER BY email;
--   -- expect 4 rows, all @regression-fixture-tenant-b.example.com
--
--   -- No .test address may survive anywhere:
--   SELECT count(*) FROM public.ts_users     WHERE email         LIKE '%.test';  -- 0
--   SELECT count(*) FROM public.ts_businesses WHERE contact_email LIKE '%.test'; -- 0
--
--   -- And the addresses must now clear the validator that rejected them:
--   python3 -c "from pydantic import BaseModel, EmailStr
--   class M(BaseModel): email: EmailStr
--   print(M(email='owner@regression-fixture-tenant-b.example.com'))"

-- ============================================================
-- ROLLBACK (restores the unusable .test addresses — only useful if
-- something outside this repo hardcoded them)
-- ============================================================
-- UPDATE public.ts_users
--    SET email = replace(email, '@regression-fixture-tenant-b.example.com',
--                               '@regression-fixture-tenant-b.test')
--  WHERE business_id = '00000000-0000-4000-b000-00000000000b';
-- UPDATE public.ts_businesses
--    SET contact_email = replace(contact_email, '@regression-fixture-tenant-b.example.com',
--                                               '@regression-fixture-tenant-b.test')
--  WHERE id = '00000000-0000-4000-b000-00000000000b';
