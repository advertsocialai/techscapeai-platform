# Prompt changelog

The `gogaga-claude-prompts` skill requires every prompt change to be recorded
here **with the observed behaviour that motivated it** — not just what changed.
A prompt edit with no recorded symptom cannot be evaluated later and cannot be
safely reverted, because nobody knows what it was fixing.

Created 2026-08-09. The skill had instructed writers to log here since it was
written, but **this file did not exist**, so the instruction was unfollowable
and no prompt history was kept. Anything changed before this date is unrecorded.

## Format

```
## YYYY-MM-DD — <prompt or file touched>
Observed: <the behaviour that prompted the change — a real transcript line, a
          wrong extraction, a latency figure. Be specific; "it felt off" is not
          a symptom anyone can re-test.>
Changed:  <what was edited>
Expected: <what should now happen>
Verified: <how it was checked, or NOT VERIFIED>
```

## Entries

_None yet. The first prompt change after 2026-08-09 goes here._
