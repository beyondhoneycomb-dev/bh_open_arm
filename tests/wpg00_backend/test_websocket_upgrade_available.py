"""The served process can actually upgrade a WebSocket, not just mount the route.

Bare `uvicorn` ships no WebSocket implementation, and what it does without one is the worst
available failure: the upgrade request is answered `200 OK` instead of `101 Switching Protocols`.
Nothing errors. The route is mounted, the startup report says the realtime channel is up, and the
browser's client sees a socket that closed and reconnects every second forever.

`CTR-WS@v2`'s single channel carries the soft stop (`FR-GUI-065`), so a process that cannot
upgrade is a process with no stop path — and the only place it shows is a uvicorn WARNING in a log
nobody reads while an arm is energized.

Asserted on the resolved protocol rather than on an import, because `auto` is what the server
actually runs and it is the thing that silently degrades: an installed library the auto-selector
rejects reads exactly like no library at all.
"""

from __future__ import annotations

import pytest

# `none` is a deliberate opt-out and would satisfy an "is something configured" check while
# refusing every upgrade, which is the failure this file exists for.
DISABLED_PROTOCOL = "none"


def test_a_websocket_implementation_is_installed() -> None:
    """One of uvicorn's protocol backends is importable, or no socket can ever open."""
    from uvicorn.protocols.websockets.auto import AutoWebSocketsProtocol

    assert AutoWebSocketsProtocol is not None, (
        "uvicorn resolved no WebSocket protocol. Bare `uvicorn` ships none and answers every "
        "upgrade with 200 OK instead of 101, so the realtime channel — which carries the soft "
        "stop — never opens and the browser reconnects forever. Add `websockets` to the "
        "`server` dependency group."
    )


def test_the_default_configuration_does_not_disable_websockets() -> None:
    """`ws="none"` refuses every upgrade while looking configured.

    `oa-serve` passes no `ws=` argument, so this pins uvicorn's default rather than our call: a
    default that ever became `none` would take the stop path away with nothing in this repository
    changing.
    """
    from uvicorn.config import Config

    config = Config(app=lambda scope, receive, send: None)

    assert config.ws != DISABLED_PROTOCOL


@pytest.mark.parametrize("module", ["websockets"])
def test_the_named_implementation_is_the_one_installed(module: str) -> None:
    """The dependency `pyproject.toml` names is the one present.

    Kept separate from the auto-resolution check above so a green run says which of the two
    facts held: a different library satisfying `auto` would pass that check and leave the
    declared dependency wrong.
    """
    __import__(module)
