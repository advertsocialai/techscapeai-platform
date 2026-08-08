"""
Fire-and-forget background task helper (Phase 4 hardening — DEBT-06).

The Phase 3 services each scheduled work with a bare:

    asyncio.ensure_future(coro())        # return value discarded

which has two defects that only bite in production:

1. **The task can be garbage-collected mid-execution.** The event loop keeps
   only a *weak* reference to a running task. CPython documents this
   explicitly: if nothing else holds a strong reference, the task may vanish
   before it completes. On a busy voice call — exactly when these fire — that
   is a silently dropped sentiment score, suggestion, or post-call pipeline
   run, with nothing in the logs.

2. **Exceptions are invisible.** With no `add_done_callback`, a raise inside
   the coroutine surfaces only as a "Task exception was never retrieved"
   warning at GC time, attributed to no particular call.

`spawn()` fixes both: it holds the task in a module-level set until it
finishes, and attaches a callback that logs any exception against a caller-
supplied label. `CancelledError` is re-raised rather than logged, because a
cancelled task is a shutdown signal, not a failure.

This does NOT add a shutdown drain — a worker recycle can still lose in-flight
work. That remains open in DEBT-06; the fix here is the GC and visibility half,
which is what actually loses data silently today.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)

# Strong references to in-flight tasks. Without this the loop's weak reference
# is the only one, and the task is collectable mid-run.
_tasks: set[asyncio.Task] = set()


def _on_done(label: str):
    def _cb(task: asyncio.Task) -> None:
        _tasks.discard(task)
        if task.cancelled():
            logger.debug("background task cancelled: %s", label)
            return
        exc = task.exception()
        if exc is not None:
            logger.error("background task failed: %s", label, exc_info=exc)
    return _cb


def spawn(coro: Coroutine[Any, Any, Any], *, label: str) -> Optional[asyncio.Task]:
    """Schedule `coro` on the running loop, keeping a strong reference.

    Returns the Task, or None when there is no running loop (in which case the
    coroutine is closed so Python does not emit a "never awaited" warning).
    Never raises into the caller — these are fire-and-forget side effects and
    must not be able to break the voice path that scheduled them.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("no running event loop — background task skipped: %s", label)
        coro.close()
        return None

    try:
        task = loop.create_task(coro)
    except Exception:
        logger.exception("failed to schedule background task: %s", label)
        coro.close()
        return None

    _tasks.add(task)
    task.add_done_callback(_on_done(label))
    return task


def pending_count() -> int:
    """In-flight task count — exposed for tests and health checks."""
    return len(_tasks)
