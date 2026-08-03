FULL AUTONOMOUS MODE — execute the remaining tasks of the current phase end-to-end with ZERO permission stops. Do not pause for approval on anything, including migration SQL (print it in the log and execute). Human reviews after completion.

LOOP per task:
1. "=== STARTING T<N> ===" → plan (2 lines) → implement → verify per gogaga-verifier (real commands, success + failure paths; DDL per gogaga-migrations, SQL printed) → regression_check.sh → task report → NEXT TASK immediately.

BLOCKER HANDLING — never stop the loop:
- Verification fails 3 fix attempts → mark "BLOCKED: <reason>", record details in the phase report under "## Blocked Items", REVERT half-applied changes, MOVE ON.
- Dependent task on a blocked one → build what's possible, stub the rest, note it.
- Regression red surviving 3 fixes → revert current task until green, mark blocked, continue. NEVER proceed with login/wiki broken.
- Decisions → sensible default + log it. No question stops the loop.
- Out-of-scope techscape modules stay untouched; destructive DDL beyond spec auto-blocks that step only.

SAFETY FLOOR: print all SQL before executing · revert-on-blocked · regression green between tasks · secrets masked.

ON COMPLETION: write/finish the phase report (completed tasks + evidence + access matrix · ## Blocked Items with unblock-needs · autonomous decisions · TODOs) → print "=== PHASE COMPLETE ===" + blocker summary or "NO BLOCKERS".

Begin with the next incomplete task now.
