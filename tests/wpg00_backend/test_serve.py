"""`oa-serve` — the port default, the conflict refusal, and the absent-bundle branch.

No test here binds the service port. The conflict case takes an ephemeral port from the kernel and
holds it, so what is proven is that a bound port is refused, not that this machine happens to have
something on the default one. The availability case probes port 0, which the kernel always answers.

`uvicorn.run` is replaced wherever a test drives `main`, so a refusal that leaked through to the
server would fail loudly here instead of hanging the suite on a live socket.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.actuation.clock import WallClock
from backend.config import serve
from backend.config.arm import ARM_BACKEND_DUMMY, build_arm_session
from backend.config.constants import (
    CONFIG_ROUTE,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    SPA_BUNDLE_DIRECTORY,
    SPA_ENTRY_FILENAME,
    SUBOBJECT_LAYOUT,
)
from backend.config.store import RuntimeConfigStore
from backend.ws.deployment import LoopbackDeployment, admitted_origins
from contracts.prim.schema import ARM_SIDES

# The port `13` §2.7 and FR-GUI-006 fix as the browser<->backend default. Written out here, in the
# test, so the constant is checked against the specification rather than against itself.
SPEC_DEFAULT_PORT = 8000

# The tick thread's name, as `ArmSessionRunner` sets it. Spelled here rather than imported so the
# assertion is against the name a `ps` or a thread dump shows, not against the same constant the
# runner used.
RUNNER_NAME = "oa-arm-session"

# Liveness bound on waiting for the first published frame. The passing path returns as soon as
# the board has one.
TICK_WAIT_TIMEOUT_SEC = 5.0

# How long that wait sleeps between looks. Well under the 100 Hz default tick so no frame is
# missed, and non-zero so the wait yields the GIL to the thread it is waiting on.
BOARD_POLL_INTERVAL_SEC = 0.001

ENTRY_MARKUP = "<!doctype html><title>OpenArm</title>"
ASSET_BODY = "export const build = 1;\n"
DEEP_LINK_ROUTE = "/connection"


def build_bundle(root: Path) -> Path:
    """Write a minimal built bundle under `root`, shaped like vite's output.

    Args:
        root: Stand-in repository root.

    Returns:
        (Path) The bundle directory that was created.
    """
    bundle = root / SPA_BUNDLE_DIRECTORY
    (bundle / "assets").mkdir(parents=True)
    (bundle / SPA_ENTRY_FILENAME).write_text(ENTRY_MARKUP, encoding="utf-8")
    (bundle / "assets" / "app.js").write_text(ASSET_BODY, encoding="utf-8")
    return bundle


def refuse_to_serve(*args: Any, **kwargs: Any) -> None:
    """Stand in for `uvicorn.run` and fail if anything reaches it."""
    raise AssertionError(f"uvicorn.run was reached: {args} {kwargs}")


def test_default_port_is_the_specified_one() -> None:
    """The default is the spec's port, and it is a named constant."""
    assert DEFAULT_HTTP_PORT == SPEC_DEFAULT_PORT


def test_parser_defaults_read_from_the_constants() -> None:
    """`--port` and `--host` default to the constants, not to their own literals."""
    args = serve.build_parser().parse_args([])
    assert args.port == DEFAULT_HTTP_PORT
    assert args.host == DEFAULT_HTTP_HOST
    assert args.config_dir is None


def test_serve_module_spells_no_port_literal() -> None:
    """The port number appears nowhere in the serving module — the constant is its one spelling.

    A second copy of the number is the failure this guards: a default changed in `constants.py` and
    left behind in a docstring or a call site here produces two answers to "which port", and the
    stale one is the one an operator reads.
    """
    source = Path(serve.__file__).read_text(encoding="utf-8")
    assert str(SPEC_DEFAULT_PORT) not in source


def test_port_zero_is_available() -> None:
    """Port 0 binds by definition, so the availability branch is exercised without a fixed port."""
    assert serve.port_is_available(DEFAULT_HTTP_HOST, 0) is True


def test_a_held_port_is_not_available() -> None:
    """A port with a live listener is reported taken, SO_REUSEADDR notwithstanding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        held.bind((DEFAULT_HTTP_HOST, 0))
        held.listen(1)
        taken = held.getsockname()[1]
        assert serve.port_is_available(DEFAULT_HTTP_HOST, taken) is False


def test_conflict_refusal_names_the_port() -> None:
    """The refusal carries the port and the interface, which is what makes it actionable."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        held.bind((DEFAULT_HTTP_HOST, 0))
        held.listen(1)
        taken = held.getsockname()[1]
        with pytest.raises(serve.PortConflictError) as refused:
            serve.assert_port_available(DEFAULT_HTTP_HOST, taken)
    message = str(refused.value)
    assert str(taken) in message
    assert DEFAULT_HTTP_HOST in message


def test_available_port_passes_the_assertion() -> None:
    """The assertion is silent when the port is free — it refuses, it does not warn."""
    assert serve.assert_port_available(DEFAULT_HTTP_HOST, 0) is None


def test_main_refuses_a_taken_port_without_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A conflict exits non-zero, names the port on stderr, and never reaches the server."""
    monkeypatch.setattr(serve.uvicorn, "run", refuse_to_serve)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        held.bind((DEFAULT_HTTP_HOST, 0))
        held.listen(1)
        taken = held.getsockname()[1]
        exit_code = serve.main(
            ["--host", DEFAULT_HTTP_HOST, "--port", str(taken), "--config-dir", str(tmp_path)]
        )
    assert exit_code == serve.EXIT_REJECTED
    assert exit_code != serve.EXIT_OK
    stderr = capsys.readouterr().err
    assert str(taken) in stderr
    assert "REJECTED" in stderr


def test_absent_bundle_is_not_built(tmp_path: Path) -> None:
    """A checkout with no frontend build reports no bundle."""
    assert serve.spa_bundle_is_built(tmp_path) is False


def test_bundle_directory_without_an_entry_is_not_built(tmp_path: Path) -> None:
    """An empty output directory is not a bundle.

    This is the leftover-`dist/` case: a cleaned or interrupted vite build leaves the directory
    behind, and treating its existence as a bundle would mount static files that answer every
    route with a 404 no operator can distinguish from a routing defect.
    """
    (tmp_path / SPA_BUNDLE_DIRECTORY).mkdir(parents=True)
    assert serve.spa_bundle_is_built(tmp_path) is False


def test_absent_bundle_leaves_rest_serving(store: RuntimeConfigStore, tmp_path: Path) -> None:
    """With no bundle, nothing is mounted and the REST surface still answers."""
    app, websocket_mounted, spa_mounted = serve.build_server_app(store, root=tmp_path)
    assert spa_mounted is False
    assert websocket_mounted is False
    with TestClient(app) as client:
        assert client.get(CONFIG_ROUTE).status_code == 200


def test_built_bundle_is_mounted(store: RuntimeConfigStore, tmp_path: Path) -> None:
    """A built bundle mounts, and the entry document answers the origin root."""
    build_bundle(tmp_path)
    app, _, spa_mounted = serve.build_server_app(store, root=tmp_path)
    assert spa_mounted is True
    with TestClient(app) as client:
        assert client.get("/").text == ENTRY_MARKUP


def test_bundle_assets_are_served_as_themselves(store: RuntimeConfigStore, tmp_path: Path) -> None:
    """A real file in the bundle is served, not swallowed by the deep-link fallback."""
    build_bundle(tmp_path)
    app, _, _ = serve.build_server_app(store, root=tmp_path)
    with TestClient(app) as client:
        assert client.get("/assets/app.js").text == ASSET_BODY


def test_deep_link_resolves_to_the_entry_document(
    store: RuntimeConfigStore, tmp_path: Path
) -> None:
    """A client-side route the disk has never heard of gets the SPA, not a 404.

    `frontend/src/app/App.tsx` routes with BrowserRouter, so `/connection` only exists in the
    browser. Answering it with a 404 breaks every refresh and every pasted link.
    """
    build_bundle(tmp_path)
    app, _, _ = serve.build_server_app(store, root=tmp_path)
    with TestClient(app) as client:
        response = client.get(DEEP_LINK_ROUTE)
    assert response.status_code == 200
    assert response.text == ENTRY_MARKUP


def test_rest_survives_the_root_mount(store: RuntimeConfigStore, tmp_path: Path) -> None:
    """The REST routes still answer with the SPA mounted at `/`.

    The mount matches every path, so this is the ordering assertion: were the bundle mounted before
    the routes, `GET /api/config` would return the SPA's HTML and the browser would parse markup as
    its configuration.
    """
    build_bundle(tmp_path)
    app, _, _ = serve.build_server_app(store, root=tmp_path)
    with TestClient(app) as client:
        response = client.get(CONFIG_ROUTE)
    assert response.status_code == 200
    assert response.json()[SUBOBJECT_LAYOUT] is not None


def test_a_process_with_no_arm_mounts_no_realtime_channel(
    store: RuntimeConfigStore, tmp_path: Path
) -> None:
    """No arm, no channel — because the channel's reason to exist is the stop path.

    A route mounted here would accept a soft stop, engage a latch nobody owns, and answer the
    browser as though something had happened. `frontend/src/app/backendLink.ts` refuses to
    pretend about exactly that, and the server must not make the pretence true from its end.
    """
    app, websocket_mounted, _ = serve.build_server_app(store, root=tmp_path)

    assert websocket_mounted is False
    # Matched on class name rather than an imported type so the assertion covers both the FastAPI
    # and the starlette route classes without this test naming starlette as a dependency.
    assert _websocket_routes(app) == []


def test_an_arm_session_brings_exactly_one_realtime_channel(
    store: RuntimeConfigStore, tmp_path: Path
) -> None:
    """`CTR-WS@v2` D-2 permits one realtime socket, and the count is what proves it.

    Asserted as a count rather than as "at least one": a second realtime path would make the
    stop path two places, and that is the failure `WP-3B-15` ⑤ classifies FAIL_BLOCKING.
    """
    clock = WallClock()
    arm = build_arm_session(ARM_BACKEND_DUMMY, clock)

    app, websocket_mounted, _ = serve.build_server_app(store, root=tmp_path, arm=arm, clock=clock)

    assert websocket_mounted is True
    assert len(_websocket_routes(app)) == 1


def test_the_allowlist_names_every_loopback_spelling_of_the_served_port() -> None:
    """The operator picks the spelling by typing it, and the bind address does not decide it.

    A page reached as `http://localhost:8000` sends that as its Origin even when the server bound
    `127.0.0.1`. An allowlist naming only the bound address refuses a page this very process
    served — and the refusal reads as a security failure rather than a spelling one.
    """
    origins = serve.loopback_origins(DEFAULT_HTTP_PORT)

    assert f"http://127.0.0.1:{DEFAULT_HTTP_PORT}" in origins
    assert f"http://localhost:{DEFAULT_HTTP_PORT}" in origins
    assert f"http://[::1]:{DEFAULT_HTTP_PORT}" in origins


def test_every_admitted_origin_is_one_the_deployment_accepts() -> None:
    """The allowlist is built here and judged there; a spelling mismatch would refuse startup.

    `LoopbackDeployment` parses each entry and requires a loopback host, so a bare IPv6 address
    built without brackets is rejected at construction — which is `oa-serve` failing to start
    rather than a channel that quietly admits nobody.
    """
    deployment = LoopbackDeployment(
        host=DEFAULT_HTTP_HOST, origin_allowlist=serve.loopback_origins(DEFAULT_HTTP_PORT)
    )

    assert admitted_origins(deployment) == serve.loopback_origins(DEFAULT_HTTP_PORT)


def test_serving_ticks_the_arm_session_and_stops_it_afterwards(
    store: RuntimeConfigStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board has a writer only while the server is up, and none after it comes down.

    Both halves are one test because they are one bug in two directions. Without the start, the
    board this process publishes stays empty and the deadman is never polled — a mounted channel
    over a session nothing drives. Without the stop, a thread outlives the server it was serving
    and keeps reading an arm nobody is watching.
    """
    clock = WallClock()
    arm = build_arm_session(ARM_BACKEND_DUMMY, clock)
    assert arm is not None
    app, _, _ = serve.build_server_app(store, arm=arm, clock=clock)
    published_while_serving: list[object] = []

    def observe_then_return(_app: Any, host: str, port: int) -> None:
        """Stand in for the blocking server: watch the board, then let the caller unwind.

        The wait sleeps rather than spins. A spin holds the GIL against the tick thread it is
        waiting for, which on the parallel lane's twenty-four workers turns a healthy runner into
        a timeout.
        """
        deadline = clock.now() + TICK_WAIT_TIMEOUT_SEC
        while arm.board(ARM_SIDES[0]).view().state is None and clock.now() < deadline:
            time.sleep(BOARD_POLL_INTERVAL_SEC)
        published_while_serving.append(arm.board(ARM_SIDES[0]).view().state)

    monkeypatch.setattr(serve.uvicorn, "run", observe_then_return)

    assert serve.serve_until_stopped(app, arm, store, DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT) == 0

    assert published_while_serving[0] is not None
    assert [thread.name for thread in threading.enumerate() if thread.name == RUNNER_NAME] == []


def _websocket_routes(app: FastAPI) -> list[object]:
    """The app's realtime routes, matched by class name.

    By name rather than by an imported type so the check covers both the FastAPI and the
    starlette route classes without this test naming starlette as a dependency.
    """
    return [route for route in app.routes if "WebSocket" in type(route).__name__]
