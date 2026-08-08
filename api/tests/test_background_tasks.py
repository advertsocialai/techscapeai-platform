"""
Regression tests for DEBT-06 — fire-and-forget tasks that could be collected.

The Phase 3 services each scheduled work with a bare `asyncio.ensure_future(...)`
and discarded the handle. The event loop keeps only a weak reference to a running
task, so with nothing else holding one the task may be garbage-collected before it
finishes — silently dropping a sentiment score, a suggestion, or an entire
post-call pipeline run, with nothing in the logs. Exceptions were equally
invisible: with no done-callback, a raise surfaced only as a
"Task exception was never retrieved" warning at GC time.

`background.spawn()` holds a strong reference until completion and logs failures
against a label.
"""
from __future__ import annotations
import asyncio
import logging

import pytest

from app.services.travel import background


def test_spawn_holds_a_strong_reference_until_done():
    async def main():
        started = asyncio.Event()
        release = asyncio.Event()

        async def work():
            started.set()
            await release.wait()
            return "done"

        task = background.spawn(work(), label="test-strongref")
        assert task is not None
        await started.wait()
        # The module must be holding the reference while it runs.
        assert background.pending_count() >= 1
        release.set()
        assert await task == "done"
        await asyncio.sleep(0)  # let the done-callback run
        return background.pending_count()

    assert asyncio.run(main()) == 0, "completed task was not released"


def test_spawn_logs_exception_instead_of_swallowing_it(caplog):
    async def main():
        async def boom():
            raise ValueError("deliberate failure")

        task = background.spawn(boom(), label="test-boom")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR):
        asyncio.run(main())

    assert any(
        "test-boom" in r.getMessage() and r.exc_info for r in caplog.records
    ), "a failing background task must log with traceback"


def test_spawn_does_not_raise_into_caller():
    """A scheduling failure must never break the voice path that scheduled it."""
    async def main():
        async def boom():
            raise RuntimeError("nope")
        # Must return normally even though the coroutine will fail.
        task = background.spawn(boom(), label="test-noraise")
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(main())  # would raise if spawn propagated


def test_spawn_outside_event_loop_returns_none_and_closes_coro():
    """No running loop: return None, and close the coroutine so Python does not
    emit a spurious 'never awaited' warning."""
    async def work():
        return 1

    coro = work()
    with pytest.warns(None) if False else _noop():
        assert background.spawn(coro, label="test-noloop") is None
    # Closed coroutines cannot be awaited again.
    with pytest.raises(RuntimeError):
        asyncio.run(coro)


class _noop:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_cancelled_task_is_not_logged_as_failure(caplog):
    async def main():
        async def forever():
            await asyncio.sleep(3600)

        task = background.spawn(forever(), label="test-cancel")
        assert task is not None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR):
        asyncio.run(main())

    assert not any("test-cancel" in r.getMessage() for r in caplog.records), \
        "cancellation is a shutdown signal, not a failure"
