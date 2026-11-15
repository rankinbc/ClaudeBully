"""The in-process rate-limit wait (Phase 7 spec section 9; reconciliation C37): one helper for
``run``, ``analyze`` and Phase 5's ``plan``. A ``RateLimitExit`` has already written the pause
marker and saved state, so re-running the action resumes; the helper sleeps ``retry_after_s``
(or ``DEFAULT_WAIT_S`` when none was given) and re-runs it until the next wait would pass the
ceiling, when it re-raises and the command exits 3 as before.

``WaitMinutes`` and ``RATE_LIMIT_EXIT_CODE`` live here, beside the helper, so ``cli.py`` and the
``plan`` sub-app (``planner/cli.py``), which ``cli.py`` mounts, both import them from one module
that imports neither (preflight Q46); ``cli.py`` re-exports them."""

import time
from collections.abc import Callable
from typing import Annotated, Final

import typer

from claude_bully.runner.runner import RateLimitExit

DEFAULT_WAIT_S: Final = 15 * 60
RATE_LIMIT_EXIT_CODE: Final = 3
WaitMinutes = Annotated[
    float | None,
    typer.Option(
        "--wait-on-rate-limit",
        help="Wait inside the process for a rate window, up to this many minutes.",
    ),
]


def wait_on_rate_limit[T](
    action: Callable[[], T],
    ceiling_minutes: float | None,
    *,
    sleep: Callable[[float], None] | None = None,
    say: Callable[[str], None] | None = None,
) -> T:
    """``action()``, re-run after each rate limit until it returns or the total wait would pass
    ``ceiling_minutes``; with no ceiling the first rate limit is re-raised at once. ``sleep``
    and ``say`` default to ``time.sleep`` and ``print``, bound at call time (a default bound at
    import time would hold the real function whatever a test patched later, P26)."""
    do_sleep = sleep if sleep is not None else time.sleep
    do_say = say if say is not None else print
    waited = 0.0
    while True:
        try:
            return action()
        except RateLimitExit as exc:
            if ceiling_minutes is None:
                raise
            delay = float(exc.retry_after_s) if exc.retry_after_s else float(DEFAULT_WAIT_S)
            if waited + delay > ceiling_minutes * 60:
                raise
            do_say(
                f"rate limited ({exc}); waiting {int(delay)} s, "
                f"{int(waited + delay)} s of {int(ceiling_minutes * 60)} s"
            )
            do_sleep(delay)
            waited += delay
