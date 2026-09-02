"""pyproject.toml and requirements.txt must not drift.

Vercel's Python build runs `uv`, which installs from pyproject.toml's
[project].dependencies and ignores requirements.txt once that table exists.
Container builds (Dockerfile -> Railway) do the opposite: they
`pip install -r requirements.txt` and never read pyproject.toml.

So the two files feed two different deployments. A package added to only one
of them produces a deployment that boots fine in one place and dies at import
in the other -- which is exactly how every endpoint came to return
FUNCTION_INVOCATION_FAILED with no runtime logs (5e399fc left [project] with
no dependencies at all).

This test pins the two together. If you add a dependency, add it to both.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent

# Installed only in container builds, deliberately absent from the serverless
# bundle -- see the "Why fastembed is NOT a default dependency" note in
# pyproject.toml. Test-only packages likewise never ship to the runtime.
SERVERLESS_EXCLUDED = {"fastembed", "pytest", "pytest-cov"}


def _canonical(name: str) -> str:
    """PEP 503 normalisation, minus any extras marker."""
    name = re.split(r"[\[<>=!~;]", name, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _requirements_packages() -> set[str]:
    text = (API_DIR / "requirements.txt").read_text(encoding="utf-8")
    packages = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        packages.add(_canonical(line))
    return packages


def _pyproject_packages() -> tuple[set[str], set[str]]:
    data = tomllib.loads((API_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    runtime = {_canonical(d) for d in project.get("dependencies", [])}
    optional = {
        _canonical(d)
        for group in project.get("optional-dependencies", {}).values()
        for d in group
    }
    return runtime, optional


def test_pyproject_declares_runtime_dependencies():
    """A bare [project] table installs nothing and 500s the whole API."""
    runtime, _ = _pyproject_packages()
    assert "fastapi" in runtime, (
        "pyproject.toml [project].dependencies must list fastapi. Vercel's uv "
        "build installs from this table and ignores requirements.txt; an empty "
        "table means the deployed function cannot import fastapi and every "
        "route returns FUNCTION_INVOCATION_FAILED."
    )


def test_no_requirement_is_missing_from_pyproject():
    """Every package pip installs must be reachable from pyproject too."""
    declared = set().union(*_pyproject_packages())
    missing = _requirements_packages() - declared
    assert not missing, (
        f"in requirements.txt but not in pyproject.toml: {sorted(missing)} -- "
        "the container build would install these but the Vercel build would not."
    )


def test_no_pyproject_dependency_is_missing_from_requirements():
    """And the reverse: the container build must not be short a package."""
    runtime, optional = _pyproject_packages()
    missing = (runtime | optional) - _requirements_packages()
    assert not missing, (
        f"in pyproject.toml but not in requirements.txt: {sorted(missing)} -- "
        "the Vercel build would install these but the container build would not."
    )


def test_serverless_runtime_excludes_heavy_and_test_only_packages():
    """Keep the serverless bundle small and free of test dependencies."""
    runtime, _ = _pyproject_packages()
    leaked = runtime & SERVERLESS_EXCLUDED
    assert not leaked, (
        f"{sorted(leaked)} must stay out of [project].dependencies -- move them "
        "to an optional-dependencies group. fastembed alone pulls onnxruntime, "
        "numpy and tokenizers into the serverless bundle."
    )
