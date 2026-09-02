"""CORS must admit our own Vercel deployments and nothing else.

Read straight from the source with ast rather than importing Settings, which
would demand SUPABASE_URL and friends just to check a string.

Two things this pins down:

1. Vercel mints a new hostname per deployment, so preview origins can never be
   enumerated in ALLOWED_ORIGINS -- the regex is the only thing that admits
   them, and every frontend call fails CORS without it.
2. Vercel *truncates* the project name in per-deployment hostnames:
   "klara-customer-app" shows up as "klara-customer-67nev2c5n-...". A pattern
   written against the full project name silently misses those. That is why
   the prefixes here are short and the team suffix carries the restriction.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parent.parent / "app" / "core" / "config.py"


def _origin_regex() -> str:
    tree = ast.parse(CONFIG.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "ALLOWED_ORIGIN_REGEX"
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("ALLOWED_ORIGIN_REGEX not found in config.py")


ALLOWED = [
    # stable branch aliases
    "https://klara-customer-app-git-klara-ai-advertsocialais-projects.vercel.app",
    "https://agency-dashboard-git-klara-ai-advertsocialais-projects.vercel.app",
    "https://techscapeai-platform-git-klara-ai-advertsocialais-projects.vercel.app",
    # per-deployment hostnames, with the project name truncated by Vercel
    "https://klara-customer-67nev2c5n-advertsocialais-projects.vercel.app",
    "https://agency-dashboard-abc123xyz-advertsocialais-projects.vercel.app",
]

REJECTED = [
    "https://evil.vercel.app",
    # right project name, but not in our team scope
    "https://klara-customer-app.vercel.app",
    # right team suffix, but not one of our projects
    "https://attacker-advertsocialais-projects.vercel.app",
    # suffix appears only as a prefix of a longer attacker-controlled host
    "https://klara-x-advertsocialais-projects.vercel.app.evil.com",
    # scheme must be https
    "http://klara-customer-app-git-klara-ai-advertsocialais-projects.vercel.app",
]


@pytest.mark.parametrize("origin", ALLOWED)
def test_our_deployments_are_allowed(origin):
    assert re.match(_origin_regex(), origin), (
        f"{origin} must be allowed -- browser calls from this deployment "
        "would otherwise fail CORS preflight."
    )


@pytest.mark.parametrize("origin", REJECTED)
def test_foreign_origins_are_rejected(origin):
    assert not re.match(_origin_regex(), origin), (
        f"{origin} must NOT be allowed -- the API sends allow_credentials=True, "
        "so a matching origin can make credentialed cross-site requests."
    )


def test_regex_is_anchored_at_both_ends():
    rx = _origin_regex()
    assert rx.startswith("^") and rx.endswith("$"), (
        "an unanchored origin regex matches substrings, so "
        "https://ours.vercel.app.evil.com would pass"
    )
