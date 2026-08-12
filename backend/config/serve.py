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
bundle and an unmounted WebSocket are both reported on startup. An operator told the server came
up, who then meets a blank tab, has no way to tell which of the three happened.
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from backend.config.api import create_app
from backend.config.constants import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    SPA_BUNDLE_DIRECTORY,
    SPA_ENTRY_FILENAME,
    SPA_MOUNT_NAME,
    SPA_MOUNT_PATH,
)
from backend.config.store import RuntimeConfigStore, default_store
from backend.security.loopback import LoopbackBindError, assert_loopback_bind

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


def mount_websocket_router(_app: FastAPI) -> bool:
    """The single seam where the WebSocket router joins this process. Mounts nothing yet.

    Owner: `WP-3B-15`. That work package builds the server half of `CTR-WS@v2` and mounts its
    router here, on the app passed in, so the WebSocket shares the one port `13` §2.7 gives the
    browser. Until it lands this returns False and the process serves REST and the bundle only.

    The return value is what the startup report reads, so mounting the router and returning True
    corrects that report in the same edit. A seam that announced "mounted" from a hardcoded string
    would keep announcing it after the router was removed again.

    Args:
        _app: The application the router mounts onto. Underscored because nothing reads it yet —
            dropping the parameter instead would make WP-3B-15 change this signature and its call
            site to land a router, which is the coupling a seam exists to avoid.

    Returns:
        (bool) Whether a WebSocket route is now on the app.
    """
    return False


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
    store: RuntimeConfigStore, root: Path | None = None
) -> tuple[FastAPI, bool, bool]:
    """Assemble the one served application.

    Args:
        store: Where runtime_config lives.
        root: Repository root to resolve the bundle against, or None for this checkout.

    Returns:
        (tuple) The application, whether a WebSocket route is mounted, and whether the SPA bundle
            is mounted. The two flags are returned rather than logged here so the caller owns every
            line the operator reads.
    """
    app = create_app(store)
    websocket_mounted = mount_websocket_router(app)
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
    app, websocket_mounted, spa_mounted = build_server_app(store)

    print(f"config: {store.path}")
    if not spa_mounted:
        print(
            f"SPA bundle not built — nothing to serve at {SPA_MOUNT_PATH} "
            f"(expected {spa_bundle_directory() / SPA_ENTRY_FILENAME}; "
            f"run the frontend build). REST is serving.",
            file=sys.stderr,
        )
    if not websocket_mounted:
        print("WebSocket router not mounted (WP-3B-15) — no realtime channel.", file=sys.stderr)
    print(f"serving on http://{args.host}:{args.port}")

    uvicorn.run(app, host=args.host, port=args.port)
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
    "mount_spa_bundle",
    "mount_websocket_router",
    "port_is_available",
    "spa_bundle_directory",
    "spa_bundle_is_built",
]


if __name__ == "__main__":
    raise SystemExit(main())
