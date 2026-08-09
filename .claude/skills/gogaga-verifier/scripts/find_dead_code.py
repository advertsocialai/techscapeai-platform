#!/usr/bin/env python3
"""
Find functions that are DEFINED, correct, and NEVER CALLED.

WHY THIS EXISTS
---------------
This is the single most expensive recurring defect in this codebase. It has
landed at least four times, and each instance passed code review, type checks
and tests — because the code itself was fine. Only the wiring was missing:

  * `ai_engine.run_turn()`        — FIXED 2026-08-09. Had zero call sites, so
                                    the AI never replied during a call, while
                                    Phase 3's sentiment, whisper and scoring
                                    all ran happily on top of the silence.
                                    Now called by voice_turn_service.
  * `voice.synthesize_speech()`   — FIXED 2026-08-09, same wiring.
  * `voice.log_voice_turn()`      — FIXED 2026-08-09. The VOICE_TURN latency
                                    line had never been emitted by anything.
  * `call_feed.subscribe_call()`  — zero call sites until Phase 3. The live
                                    dashboard would have gone silent the moment
                                    Redis was provisioned.
  * `match_travel_transcripts()`  — zero Python callers. Dead RPC.

A passing test suite cannot catch this: nothing fails, the feature is simply
absent. Grep can, in seconds.

The repo is currently CLEAN — this script reports zero. It stays clean only if
someone runs it. `api/tests/test_voice_turn_loop.py` now asserts the WIRING of
the voice loop (not just its behaviour) so that particular regression turns a
test red instead of going quiet again.

USAGE
    python3 find_dead_code.py                 # scan api/app
    python3 find_dead_code.py --path api/app/services/travel
    python3 find_dead_code.py --min-lines 15  # only flag substantial functions

EXIT CODES
    0  nothing suspicious
    1  candidates found (review each — see FALSE POSITIVES below)

FALSE POSITIVES — read before "fixing" anything
    Route handlers, pytest tests, `__init__`/dunders, Pydantic validators and
    anything reached only by decorator or by string name are filtered out
    below, but the filter is heuristic. A hit is a QUESTION ("who calls this?"),
    never a verdict. Deleting a function because this script listed it is
    exactly the wrong response — the usual correct fix is to CALL it.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

# Reached by a framework, not by a caller we can see.
DECORATOR_HINTS = (
    "router.", "app.", "validator", "field_validator", "model_validator",
    "fixture", "task", "lru_cache", "property", "staticmethod", "classmethod",
    "contextmanager", "asynccontextmanager", "hookimpl",
)

SKIP_NAME_PREFIXES = ("test_", "_")  # tests + private helpers


def function_defs(tree: ast.AST, path: Path) -> list[tuple[str, int, int]]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith(SKIP_NAME_PREFIXES) or node.name.startswith("__"):
            continue
        decs = " ".join(ast.unparse(d) for d in node.decorator_list)
        if any(h in decs for h in DECORATOR_HINTS):
            continue
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        out.append((node.name, node.lineno, end - node.lineno + 1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="api/app")
    ap.add_argument("--min-lines", type=int, default=5,
                    help="ignore functions shorter than this (default 5)")
    args = ap.parse_args()

    root = Path(args.path)
    if not root.exists():
        sys.exit(f"path not found: {root}")

    files = [p for p in root.rglob("*.py") if "__pycache__" not in str(p)]
    # One concatenated corpus: a call from ANY file counts as a call.
    corpus = "\n".join(p.read_text(encoding="utf8", errors="ignore") for p in files)

    findings = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf8", errors="ignore"))
        except SyntaxError:
            continue
        for name, lineno, length in function_defs(tree, path):
            if length < args.min_lines:
                continue
            # Count every mention, then subtract the definition itself.
            mentions = len(re.findall(rf"\b{re.escape(name)}\b", corpus))
            defs = len(re.findall(rf"\bdef\s+{re.escape(name)}\b", corpus))
            if mentions - defs <= 0:
                findings.append((str(path), lineno, name, length))

    if not findings:
        print("No uncalled functions found.")
        return 0

    print(f"{len(findings)} function(s) defined but never referenced elsewhere:\n")
    for path, lineno, name, length in sorted(findings, key=lambda f: -f[3]):
        print(f"  {path}:{lineno}  {name}()  ({length} lines)")
    print(
        "\nEach is a QUESTION, not a verdict: who should be calling this?\n"
        "The usual correct fix is to WIRE IT UP, not to delete it — every past\n"
        "instance in this repo was a missing call, not dead weight."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
