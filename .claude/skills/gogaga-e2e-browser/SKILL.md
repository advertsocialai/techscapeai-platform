---
name: gogaga-e2e-browser
description: "Real-browser verification for GoGaga's two frontends (agency-dashboard/, customer-app/) — accessibility sweeps (axe-core WCAG 2 A/AA) and "Postgres-to-screen" proof that real data actually renders in a real UI, not just that the API returns 200. ALWAYS use this skill when a task claims a UI screen is "done," "live-verified," or "accessible," when running against the local_seam harness, or when the words axe, accessibility, WCAG, Chromium, or "postgres to screen" appear. This skill exists because that verification has been done successfully before (wave-2, 34/34 routes, 0 violations) but AD HOC — no script or CI step captures it, so it is not repeatable without this skill. Fix that: every future accessibility/visual claim should route through a saved, re-runnable check, not a one-off browser session."
---

# GoGaga Browser-Driven Verification (E2E + Accessibility)

## Why this skill exists

`GOGAGA_ANALYSIS_REPORT.md` and `PLATFORM_STATUS.md` both cite a real, successful accessibility sweep: **axe-core, WCAG 2 A/AA, all 34 routes across both apps, 0 violations** — plus a genuine "Postgres → screen" proof (real signup/login/lead/booking rows rendering correctly in Chromium against the `local_seam` harness, per `scripts/local_seam/README.md`). Both of these are strong evidence, and both were produced by **driving a real browser in an ad-hoc session with no saved script, no test file, and no CI step**. If that session's environment is gone, so is the ability to reproduce either claim. That is the gap this skill closes: turn a one-time browser session into a repeatable check.

## Two distinct verification types — don't conflate them

1. **API-level verification** (`gogaga-verifier`'s job): does the endpoint return the right status code and body? This tells you nothing about whether the data actually renders correctly in the UI, whether a form field is unlabeled, or whether a button is unreachable by keyboard.
2. **Browser-level verification** (this skill's job): does a real browser, loading the real built frontend against real data, actually show the right thing and pass accessibility checks? A screen can be "100% built" by `gogaga-frontend`'s standard and still fail here (that's exactly what happened before the accessibility fixes noted in the scoreboard — an unnamed password-eye button and 15 unlabeled selects were real bugs API tests couldn't catch).

Both are required before calling a screen "done." Neither substitutes for the other.

## Setting up a repeatable browser session

The sandbox this project develops in has no persistent GUI browser by default. The fastest way to make browser-driven checks repeatable across sessions is the **Playwright MCP server** (Microsoft's official `@playwright/mcp`), which lets Claude Code drive a real Chromium instance via natural-language / structured calls instead of an ad-hoc one-off:

```bash
claude mcp add playwright npx @playwright/mcp@latest
```

Once added, prefer it over any bespoke browser-launch code for this kind of verification — it persists across sessions (`~/.claude.json`), reads pages via accessibility snapshots (which pairs naturally with an accessibility-audit workflow), and can drive both `agency-dashboard` and `customer-app` against the `local_seam` harness or a real deploy.

## Workflow: Postgres-to-screen proof

1. Bring up `scripts/local_seam` per its README (local Postgres 16 + pgvector, all migrations applied, `postgrest_shim.py` running) — or point at a real deploy if credentials/network allow.
2. Seed one real row per key entity the screen depends on (a lead, a booking, a payment link — whatever the screen reads) through the **real API**, never by hand-inserting rows that skip the app's own write path.
3. Drive the browser through the real login/OTP flow — never bypass auth to "just check the render," since that's exactly the kind of shortcut that would have hidden the turn-loop-style bugs this project has already been burned by once.
4. Assert the seeded data appears correctly on screen (not just "page loaded without a JS error" — read the actual rendered values).
5. **Save what you did.** At minimum, append the routes covered, the date, and what was seeded to `PLATFORM_STATUS.md` under an Accessibility/E2E evidence section, the same discipline `gogaga-scoreboard` already expects for score changes. Where practical, save the Playwright script/commands themselves under `scripts/` so the next session can re-run rather than re-derive them.

## Workflow: accessibility sweep

1. Same setup as above — real data, real auth, real rendered screen (a sweep against a stub/empty state under-tests real interactive elements like data tables and select-with-options).
2. Run an axe-core scan against each route. If using the Playwright MCP browser, this can be done by injecting `axe-core` and reading its report, or by pairing with `@axe-core/playwright` if it's added as a dev dependency (it is not currently in either app's `package.json` — consider adding it if repeat sweeps are wanted rather than re-injecting the script every session).
3. Cover **all** routes in both apps, not a sample — the prior sweep's value came specifically from being exhaustive (34/34). A partial sweep that gets reported as "accessibility: done" is worse than an honest "partial," per the same standard `gogaga-scoreboard` holds score claims to.
4. Also do a keyboard-only pass on the interactive-heavy screens (forms, tables with row actions, the Live Call / takeover UI) — tab order and reachability, not just axe's automated ruleset, since axe cannot catch every keyboard-trap or focus-order issue.
5. Log violations found, the fix, and re-scan to confirm 0 remaining — don't report "0 violations" without the fix commit it followed.

## Reporting standard

Match `gogaga-scoreboard`'s honesty bar: report exactly what was covered (which routes, which app, real data or seeded, what auth state) and what was NOT covered (e.g. "not claimed: manual screen-reader certification" — the existing report already models this well; keep doing it). Never let "ran axe once, it passed" become "accessibility is done forever" — re-run after any UI change that touches forms, focus order, or color tokens.
