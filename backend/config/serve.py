"""The one process that serves the GUI: SPA bundle, REST and the WebSocket on one port.

Registered as `oa-serve`. `01` FR-SYS-002 embeds LeRobot in the backend process and forbids
spawning the `lerobot-*` CLIs, because each of those calls `connect()` on entry and `disconnect()`
on exit and `connect()` writes the arm's current pose as the zero point — so a second serving
process is a second zero point. One process is not a packaging preference here; it is the
structural half of FR-SYS-001.

`13` §2.7 puts the SPA bundle, the REST surface and the single WebSocket behind one configurable
port (FR-GUI-006). `backend.config.api.create_app` builds the REST routes and deliberately binds
nothing, so something has to own the socket: this module is that owner, and the only place in the
tree that opens a listening port.

Nothing here is allowed to fail quietly, because every failure it can have looks like a working
server from the outside. The port being taken is refused before anything is served; a missing
bundle, an absent realtime channel and a synthetic arm are all reported on startup. An operator
told the server came up, who then meets a blank tab or a board full of numbers from nothing, has
no way to tell which of them happened.

Which arm this process holds is `--arm`, and the realtime channel exists exactly when an arm
session does. That ordering is the safety property: the channel carries the soft stop, and a stop
is worth having only when something here reads the latch it engages.
"""

from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from backend.actuation.clock import Clock, WallClock
from backend.actuation.session import ArmSession
from backend.actuation.session_runner import RUNNER_STOP_JOIN_TIMEOUT_SEC, ArmSessionRunner
from backend.camera.api import mount_camera_routes
from backend.camera.cli import RIG_SLOTS
from backend.config.api import create_app
from backend.config.arm import (
    ARM_BACKEND_NONE,
    ARM_BACKENDS,
    ARM_BACKENDS_ON_HARDWARE,
    ArmBackend,
    ArmChannelsUnavailableError,
    build_arm_backend,
)
from backend.config.constants import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    SPA_BUNDLE_DIRECTORY,
    SPA_ENTRY_FILENAME,
    SPA_MOUNT_NAME,
    SPA_MOUNT_PATH,
)
from backend.config.store import RuntimeConfigStore, default_store
from backend.security.constants import PLAINTEXT_HTTP_SCHEME
from backend.security.loopback import LOOPBACK_HOSTS, LoopbackBindError, assert_loopback_bind
from backend.system.api import mount_system_routes
from backend.ws.app import mount_realtime_channel
from backend.ws.arm_channel import refuse_command
from backend.ws.constants import TELEMETRY_STALE_TICK_MULTIPLE
from backend.ws.deployment import LoopbackDeployment

EXIT_OK = 0
EXIT_REJECTED = 1

# The repository root, from this file's location rather than the working directory: `oa-serve` is
# run from wherever the operator happens to stand, and the bundle does not move when they do.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class PortConflictError(RuntimeError):
    """The configured port is already bound, so this process must not start.

    Its own type rather than a bare OSError: the caller refuses on this and only this, and an
    OSError from anywhere else in startup means something different and must not be reported to
    the operator as a port conflict.
    """


class SpaBundleFiles(StaticFiles):
    """The built bundle, with every non-file path answered by the SPA entry document.

    The SPA routes on the client (`frontend/src/app/App.tsx` uses BrowserRouter), so `/connection`
    is a path the browser owns and the disk has never heard of. Plain `StaticFiles` 404s it, which
    breaks every deep link and every refresh; resolving unknown paths to the entry document is what
    hands routing back to the client. A missing asset therefore answers with HTML instead of a 404,
    which is the accepted cost of client-side routing and shows up as a console parse error rather
    than a silently blank screen.
    """

    def __init__(self, directory: Path) -> None:
        super().__init__(directory=directory, html=True)
        self.bundle_directory = directory

    async def get_response(self, path: str, scope: Any) -> Response:
        """Serve `path` when it is a real file in the bundle, otherwise the entry document."""
        if not (self.bundle_directory / path).is_file():
            path = SPA_ENTRY_FILENAME
        return await super().get_response(path, scope)


def spa_bundle_directory(root: Path | None = None) -> Path:
    """The directory the built SPA is expected in.

    Args:
        root: Repository root to resolve against, or None for this checkout.

    Returns:
        (Path) The bundle directory, which may not exist.
    """
    base = root if root is not None else _REPO_ROOT
    return base / SPA_BUNDLE_DIRECTORY


def spa_bundle_is_built(root: Path | None = None) -> bool:
    """Whether a usable bundle is on disk.

    The entry document is the test, not the directory: vite's output directory survives a cleaned
    build and an interrupted one, and both leave a directory that serves nothing.

    Args:
        root: Repository root to resolve against, or None for this checkout.

    Returns:
        (bool) True when the bundle can be served.
    """
    return (spa_bundle_directory(root) / SPA_ENTRY_FILENAME).is_file()


def spa_bundle_built_at(root: Path | None = None) -> datetime | None:
    """When the bundle on disk was written, or None when there is none.

    The entry document's mtime, for the same reason `spa_bundle_is_built` reads that file rather
    than the directory. Reported because nothing else can tell an operator that the bundle is old:
    the gate deliberately no longer writes here, so a checkout can serve a bundle from before the
    working tree moved and look exactly like one built a minute ago.

    Args:
        root: Repository root to resolve against, or None for this checkout.

    Returns:
        (datetime | None) Local modification time of the entry document.
    """
    entry = spa_bundle_directory(root) / SPA_ENTRY_FILENAME
    if not entry.is_file():
        return None
    return datetime.fromtimestamp(entry.stat().st_mtime)


def port_is_available(host: str, port: int) -> bool:
    """Whether `port` on `host` can be bound right now.

    The probe sets SO_REUSEADDR because uvicorn does: the question this answers is not "is the port
    free by some general definition" but "will the server that runs next manage to bind", and a
    probe with different socket options answers a different question. Binding an actively listening
    port fails even with the option set, which is the case that matters.

    A port can still be taken in the moment between this probe closing and uvicorn binding. That
    window is not closed here, and it is not the failure FR-GUI-006 is about — a second `oa-serve`,
    or an unrelated service already holding the port, is caught, and that is what an operator hits.

    Args:
        host: The interface the server will bind.
        port: The port the server will bind; 0 asks the kernel for any free port.

    Returns:
        (bool) True when a bind succeeded.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def assert_port_available(host: str, port: int) -> None:
    """Refuse to continue when the port is already bound.

    Args:
        host: The interface the server will bind.
        port: The port the server will bind.

    Raises:
        PortConflictError: When the port is taken. The message names the port and the interface,
            because "address already in use" without them sends the operator looking through every
            service on the host.
    """
    if port_is_available(host, port):
        return
    raise PortConflictError(
        f"port {port} on {host} is already in use — stop whatever holds it "
        f"(another oa-serve is the usual answer) or pass --port"
    )


def loopback_origins(port: int) -> tuple[str, ...]:
    """Every Origin a page served by this machine on `port` can stamp.

    All three loopback spellings are admitted because the operator picks one by typing it, and
    which one they type is not something the bind address decides: a server on `localhost` is
    reached as `127.0.0.1` and as `[::1]` by the same browser. Naming only the bound address
    would refuse a page this very process served.

    None of them widens what is trusted. `NORM-015`'s allowlist exists to keep a page served from
    *elsewhere* off the control socket, and every entry here is a page served from here.

    Args:
        port: The port the SPA, REST and the WebSocket share.

    Returns:
        (tuple[str, ...]) The exact Origins the handshake admits.
    """
    return tuple(
        f"{PLAINTEXT_HTTP_SCHEME}://{_as_url_host(host)}:{port}" for host in LOOPBACK_HOSTS
    )


def _as_url_host(host: str) -> str:
    """Spell a bind address the way a URL does.

    `LOOPBACK_HOSTS` holds bind addresses and an IPv6 address is bare there and bracketed in a
    URL. Derived rather than kept as a second list: two copies of the same three hosts drift, and
    the one that drifts is the one nobody tests, so an Origin built from the bind spelling would
    match nothing a browser ever sends.

    Args:
        host: A bind address.

    Returns:
        (str) The host as a URL authority writes it.
    """
    return f"[{host}]" if ":" in host else host


def mount_websocket_router(
    app: FastAPI, arm: ArmSession | None, clock: Clock, port: int, control_tick_hz: float
) -> bool:
    """Mount the realtime channel over this process's arm session, if it has one.

    The order is the safety property, not a preference. The channel carries the soft stop, and a
    stop is worth having only when something in this process reads the latch it engages — so the
    route exists exactly when an arm session does. Mounting it over a latch with no owner would
    hand the operator a control that reports success and changes nothing, which is what
    `NORM-007` forbids and what `frontend/src/app/backendLink.ts` refuses to pretend about.

    The session is passed rather than reached for: it is the same object that must be the
    `latch_target` and the owner of the `deadman`, and passing one object is what makes a second
    latch unconstructible here.

    Args:
        app: The application the route mounts onto, so the WebSocket shares the one port
            `13` §2.7 gives the browser.
        arm: This process's arm session, or None when it holds no arm.
        clock: The server monotonic clock latch timestamps are stamped from — the same one the
            session's boards and lease read.
        port: The served port, used to build the Origin allowlist.
        control_tick_hz: The rate the session is ticked at, which is what makes a board age
            readable: the deadline the frame calls a side stale by is that period times
            `TELEMETRY_STALE_TICK_MULTIPLE`. Passed rather than defaulted because an operator
            who lowered the tick rate would otherwise get stale reported on a healthy arm.

    Returns:
        (bool) Whether a WebSocket route is now on the app.
    """
    if arm is None:
        return False
    mount_realtime_channel(
        app,
        latch_target=arm,
        deadman=arm.deadman,
        clock=clock,
        command_sink=refuse_command,
        security=LoopbackDeployment(
            host=DEFAULT_HTTP_HOST, origin_allowlist=loopback_origins(port)
        ),
        # The boards this process writes, so a connected client is sent what they hold. Passed
        # here and nowhere else: a channel mounted without them sends nothing unprompted, which
        # is the shape every refusal test reads against.
        boards={side: arm.board(side) for side in arm.sides},
        stale_after_s=TELEMETRY_STALE_TICK_MULTIPLE / control_tick_hz,
    )
    return True


def mount_spa_bundle(app: FastAPI, root: Path | None = None) -> bool:
    """Mount the built bundle at the origin root, if it is built.

    Registered by the caller after the REST routes and the WebSocket: the mount path matches every
    request, so anything added afterwards is unreachable.

    Args:
        app: The application to mount onto.
        root: Repository root to resolve the bundle against, or None for this checkout.

    Returns:
        (bool) Whether the bundle was mounted. False means it is not built, which is a normal
            state on a fresh clone and leaves the REST surface serving.
    """
    if not spa_bundle_is_built(root):
        return False
    app.mount(
        SPA_MOUNT_PATH,
        SpaBundleFiles(directory=spa_bundle_directory(root)),
        name=SPA_MOUNT_NAME,
    )
    return True


def build_server_app(
    store: RuntimeConfigStore,
    root: Path | None = None,
    arm: ArmSession | None = None,
    clock: Clock | None = None,
    port: int = DEFAULT_HTTP_PORT,
) -> tuple[FastAPI, bool, bool]:
    """Assemble the one served application.

    Args:
        store: Where runtime_config lives.
        root: Repository root to resolve the bundle against, or None for this checkout.
        arm: This process's arm session, or None when it holds no arm. None is the default so a
            caller that has not chosen a backend gets the REST surface and the bundle rather than
            a control channel over a latch nobody owns.
        clock: The server monotonic clock, or None for a fresh `WallClock`. Supplied by the
            caller that also built `arm`, because the two must be the same clock — an expiry
            judged on one and a latch stamped from another cannot be ordered against each other.
        port: The served port, which decides the Origin allowlist.

    Returns:
        (tuple) The application, whether a WebSocket route is mounted, and whether the SPA bundle
            is mounted. The two flags are returned rather than logged here so the caller owns every
            line the operator reads.
    """
    app = create_app(store)
    mount_camera_routes(app, store.directory, tuple(RIG_SLOTS))
    mount_system_routes(app)
    websocket_mounted = mount_websocket_router(
        app,
        arm,
        clock if clock is not None else WallClock(),
        port,
        store.load().document.control.control_tick_hz,
    )
    spa_mounted = mount_spa_bundle(app, root)
    return app, websocket_mounted, spa_mounted


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        (argparse.ArgumentParser): Parser for the serving options.
    """
    parser = argparse.ArgumentParser(prog="oa-serve", description=__doc__)
    parser.add_argument(
        "--host",
        default=DEFAULT_HTTP_HOST,
        help="interface to bind (default: loopback)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="port shared by the SPA, REST and the WebSocket",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="directory holding runtime_config.json (default: the XDG config directory)",
    )
    parser.add_argument(
        "--arm",
        choices=ARM_BACKENDS,
        default=ARM_BACKEND_NONE,
        help=(
            "which arm this process holds. 'none' serves REST and the bundle with no realtime "
            "channel; 'dummy' opens no bus and puts synthetic readings on the board"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Serve the GUI, or refuse before serving anything.

    Args:
        argv: Argument vector; defaults to `sys.argv[1:]`.

    Returns:
        (int): Process exit code; non-zero when the port was already taken.
    """
    args = build_parser().parse_args(argv)

    # Checked before the port, and before anything binds. This process serves the control
    # channel in plaintext under `NORM-015`, and that ruling holds only while the bind is
    # loopback — so the refusal is a precondition of starting, not a warning printed beside a
    # server that is already listening.
    try:
        assert_loopback_bind(args.host)
    except LoopbackBindError as refused:
        print(f"REJECTED: {refused}", file=sys.stderr)
        return EXIT_REJECTED

    try:
        assert_port_available(args.host, args.port)
    except PortConflictError as conflict:
        print(f"REJECTED: {conflict}", file=sys.stderr)
        return EXIT_REJECTED

    store = (
        default_store() if args.config_dir is None else RuntimeConfigStore(Path(args.config_dir))
    )
    clock = WallClock()
    try:
        backend = build_arm_backend(args.arm, clock)
    except (ValueError, ArmChannelsUnavailableError) as refused:
        print(f"REJECTED: {refused}", file=sys.stderr)
        return EXIT_REJECTED
    arm = backend.session
    app, websocket_mounted, spa_mounted = build_server_app(
        store, arm=arm, clock=clock, port=args.port
    )

    print(f"config: {store.path}")
    built_at = spa_bundle_built_at()
    if spa_mounted and built_at is not None:
        print(f"SPA bundle: {spa_bundle_directory()} (built {built_at:%Y-%m-%d %H:%M:%S})")
    if not spa_mounted:
        print(
            f"SPA bundle not built — nothing to serve at {SPA_MOUNT_PATH} "
            f"(expected {spa_bundle_directory() / SPA_ENTRY_FILENAME}; "
            f"run the frontend build). REST is serving.",
            file=sys.stderr,
        )
    if not websocket_mounted:
        print(
            "no arm session (--arm none) — no realtime channel, so the GUI has no stop path.",
            file=sys.stderr,
        )
    elif args.arm in ARM_BACKENDS_ON_HARDWARE:
        # The other direction of the same duty. Nothing here is synthetic, and the line an
        # operator needs is the one about the motors: the vendor bus's connect handshake enabled
        # every one of them, and they stay enabled for as long as this process runs.
        print(
            f"arm backend {args.arm!r} — the bus is OPEN and every motor is ENERGIZED. "
            "Nothing commands them and they hold nothing, so the arm is limp and one frame "
            "from moving. Support it before you start this and until you stop it.",
            file=sys.stderr,
        )
    else:
        # Said on every start rather than once, and on stderr beside the other degradations. The
        # board carries numbers that look exactly like a reading and came from no arm; an
        # operator who missed one line at startup has no second chance to tell them apart.
        print(
            f"arm backend {args.arm!r} — the state board carries synthetic readings, not an arm.",
            file=sys.stderr,
        )
    print(f"serving on http://{args.host}:{args.port}")

    return serve_until_stopped(app, backend, store, args.host, args.port)


def serve_until_stopped(
    app: FastAPI, backend: ArmBackend, store: RuntimeConfigStore, host: str, port: int
) -> int:
    """Run the server, with the arm session's tick running beside it for exactly as long.

    The runner is started here rather than from an application startup hook, because the thing it
    must not outlive is this call: `uvicorn.run` blocks until the server is done, and a `finally`
    around it stops the tick on every exit — a clean shutdown, a bind that failed inside uvicorn,
    or a KeyboardInterrupt. A startup hook would tie the tick to the ASGI lifespan instead, and a
    `TestClient` entering that lifespan would start a real kernel timer inside a test.

    The backend is closed after the tick stops and never before: closing it disables torque and
    shuts the buses, and a tick still running would then be reading a socket that is gone. The
    close runs even when the runner would not stop, because a thread that outlived its join is
    the case where the motors most need to be told.

    Args:
        app: The assembled application.
        backend: The built arm backend — the session to tick, and what closing it takes.
        store: Where the control tick rate is read from.
        host: The interface to bind.
        port: The port to bind.

    Returns:
        (int) The process exit code.
    """
    arm = backend.session
    if arm is None:
        try:
            uvicorn.run(app, host=host, port=port)
        finally:
            backend.close()
        return EXIT_OK
    runner = ArmSessionRunner(arm, store.load().document.control.control_tick_hz)
    runner.start()
    try:
        uvicorn.run(app, host=host, port=port)
    finally:
        if not runner.stop():
            print(
                "the arm session tick did not stop within "
                f"{RUNNER_STOP_JOIN_TIMEOUT_SEC}s; it is still reading the arm.",
                file=sys.stderr,
            )
        if runner.failure is not None:
            print(f"the arm session tick died: {runner.failure}", file=sys.stderr)
        backend.close()
    return EXIT_OK


__all__ = [
    "EXIT_OK",
    "EXIT_REJECTED",
    "PortConflictError",
    "SpaBundleFiles",
    "assert_port_available",
    "build_parser",
    "build_server_app",
    "main",
    "loopback_origins",
    "mount_spa_bundle",
    "spa_bundle_built_at",
    "mount_websocket_router",
    "port_is_available",
    "serve_until_stopped",
    "spa_bundle_directory",
    "spa_bundle_is_built",
]


if __name__ == "__main__":
    raise SystemExit(main())
