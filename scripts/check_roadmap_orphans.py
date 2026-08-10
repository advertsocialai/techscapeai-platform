#!/usr/bin/env python3
"""
Orphan-reference check between BLOCKERS.md (the ledger) and GO_LIVE_ROADMAP.md
(the sequence). See .claude/skills/gogaga-golive-roadmap/SKILL.md.

Two failure modes this catches, both real bugs that shipped before this
script existed:

1. An ACTIVE blocker (status is OPEN/STUBBED/AWAITING/DEBT, not RESOLVED) has
   no phase in the roadmap — a reader working top-to-bottom would never see
   it. "Active" uses each ID's LAST row in BLOCKERS.md, since the ledger
   appends resolution rows rather than mutating the original (grep for a
   duplicate ID and you'll find both).

2. The roadmap references an ID (BLK-7, B-P2-03, ...) that has no row in
   BLOCKERS.md at all — a reader who clicks through finds nothing. This is
   how BLK-1..BLK-5 were found missing from the ledger entirely: referenced
   throughout GO_LIVE_ROADMAP.md and GOGAGA_ANALYSIS_REPORT.md, never given
   a row of their own.

RESOLVED IDs are correctly allowed to be absent from the roadmap — completed
work doesn't need a "what to do next" entry. IDs whose ledger row is stale
(the work was actually done under a different ID, e.g. DEBT-04 superseded by
DEBT-20) are handled as documented footnotes in the roadmap, not code
exceptions here — this script only checks presence, not semantic staleness.

Usage:
  python3 scripts/check_roadmap_orphans.py
Exit 0 = no orphans either direction. Exit 1 = orphans found, printed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "BLOCKERS.md"
ROADMAP = ROOT / "GO_LIVE_ROADMAP.md"

ID_RE = re.compile(r"\b(?:BLK-\d+|B-[A-Za-z0-9]+-\d+|DEBT-\d+)\b")
ROW_RE = re.compile(r"^\|\s*([A-Za-z0-9-]+)\s*\|")
# A row counts as still-active unless its status cell says RESOLVED. Ledger
# rows without one of these keywords (e.g. the header separator, "ID") are
# skipped entirely — this check is deliberately permissive about row shape.
ACTIVE_KEYWORDS = ("OPEN", "STUBBED", "AWAITING", "DEBT")


def ledger_statuses() -> dict[str, str]:
    """Map of ID -> status of its LAST row in BLOCKERS.md (later rows win)."""
    statuses: dict[str, str] = {}
    for line in LEDGER.read_text().splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        id_ = m.group(1)
        if id_ in ("ID", "---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        statuses[id_] = cells[-1]
    return statuses


def is_active(status: str) -> bool:
    if "RESOLVED" in status:
        return False
    return any(kw in status for kw in ACTIVE_KEYWORDS)


def main() -> int:
    if not LEDGER.exists() or not ROADMAP.exists():
        print(f"Missing {LEDGER.name} or {ROADMAP.name} — nothing to check.", file=sys.stderr)
        return 1

    statuses = ledger_statuses()
    ledger_ids = set(statuses)
    active_ids = {id_ for id_, s in statuses.items() if is_active(s)}
    roadmap_ids = set(ID_RE.findall(ROADMAP.read_text()))

    no_phase_home = sorted(active_ids - roadmap_ids)
    no_ledger_row = sorted(roadmap_ids - ledger_ids)

    ok = True
    if no_phase_home:
        ok = False
        print(f"✗ {len(no_phase_home)} active blocker(s) with no phase in {ROADMAP.name}:")
        for id_ in no_phase_home:
            print(f"    {id_}: {statuses[id_]}")
        print(f"  Fix: add a reference in the phase matching its real dependency,")
        print(f"  not wherever is convenient — see the skill's sequencing discipline.")

    if no_ledger_row:
        ok = False
        print(f"✗ {len(no_ledger_row)} roadmap reference(s) with no row in {LEDGER.name}:")
        for id_ in no_ledger_row:
            print(f"    {id_}")
        print(f"  Fix: add a ledger row for the ID, styled like its neighbors.")

    if ok:
        print(f"✓ {len(active_ids)} active blocker(s), all referenced in {ROADMAP.name}; "
              f"{len(roadmap_ids)} roadmap references, all have a {LEDGER.name} row.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
