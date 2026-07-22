"""The immersive-ar session handler: single-arm mode and profile logging (WP-3B-08).

This is the offline half of the WebXR session — the part that does not need a
headset browser. It fixes the session configuration (`immersive-ar` mode, reference
space, pose space, TLS endpoint), and on `begin` it does the two things the upstream
path gets wrong:

- ⑤ it logs the FULL `session.inputSources[*].profiles` array of every input source,
  because the Quest 3S's reported strings are the only way to confirm the fallback
  chain against real hardware (`05` §2.7, `FR-TEL-016`, `05` §5 U-6);
- ④ it admits SINGLE-ARM sessions. Upstream `ar.js` drops every frame while
  `inputSources.length < 2`, which makes right-only or left-only operation
  impossible (`05` §2.7 ⓓ, `FR-TEL-020`). Here the required arms are exactly the
  sides the teleop mode is active on, so a right-only mode begins with one source.

Opening the real session (`navigator.xr.requestSession('immersive-ar')`, live pose
frames) needs a headset browser and is deferred (`backend.teleop.webxr.reverify`).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from backend.teleop.webxr.constants import (
    POSE_SPACE_DEFAULT,
    POSE_SPACES,
    REFERENCE_SPACE_DEFAULT,
    REFERENCE_SPACES,
    SESSION_MODE,
)
from backend.teleop.webxr.gamepad import GamepadState
from backend.teleop.webxr.profiles import ProfileResolution, resolve_layout
from backend.teleop.webxr.tls import TlsConfig

_LOGGER = logging.getLogger(__name__)


class Handedness(StrEnum):
    """Which arm an input source drives. Values match the `CTR-PRIM@v1` arm sides."""

    LEFT = "left"
    RIGHT = "right"


class TeleopMode(StrEnum):
    """The arm coverage of a session, aligned with IK `--mode` (`FR-TEL-020`).

    `RIGHT`/`LEFT` are single-arm; `BIMANUAL` needs both. `active_sides` is the set of
    arms the mode requires an input source for, and it is the whole of single-arm
    support: a `RIGHT` session requires exactly the right source and no more.
    """

    RIGHT = "right"
    LEFT = "left"
    BIMANUAL = "bimanual"

    @property
    def active_sides(self) -> tuple[Handedness, ...]:
        """The arms this mode requires an input source for, in left-then-right order."""
        if self is TeleopMode.RIGHT:
            return (Handedness.RIGHT,)
        if self is TeleopMode.LEFT:
            return (Handedness.LEFT,)
        return (Handedness.LEFT, Handedness.RIGHT)

    @property
    def is_single_arm(self) -> bool:
        """Whether this mode drives one arm (RIGHT or LEFT)."""
        return self is not TeleopMode.BIMANUAL


class SessionError(ValueError):
    """Raised when a session cannot begin over the supplied input sources."""


@dataclass(frozen=True)
class InputSource:
    """One WebXR input source: its arm, its reported profiles, and its gamepad.

    Attributes:
        handedness: The arm this source drives.
        profiles: The `inputSource.profiles` strings, most-specific first.
        gamepad: The controller gamepad sampled from this source.
    """

    handedness: Handedness
    profiles: Sequence[str]
    gamepad: GamepadState


@dataclass(frozen=True)
class SessionConfig:
    """The immersive-ar session configuration.

    Attributes:
        mode: The arm-coverage mode (single-arm or bimanual).
        tls: The HTTPS/WSS endpoint the session is served on.
        session_mode: The XR session mode; fixed to `immersive-ar`.
        reference_space: The reference space requested (`viewer` by default).
        pose_space: The input-source space poses are read from (`gripSpace` default).
    """

    mode: TeleopMode
    tls: TlsConfig
    session_mode: str = SESSION_MODE
    reference_space: str = REFERENCE_SPACE_DEFAULT
    pose_space: str = POSE_SPACE_DEFAULT

    def __post_init__(self) -> None:
        """Reject a config whose session/reference/pose space is not a known value.

        Raises:
            SessionError: If the session mode is not `immersive-ar`, or the reference
                space or pose space is outside the values the WebXR path supports.
        """
        if self.session_mode != SESSION_MODE:
            raise SessionError(
                f"WebXR path opens an {SESSION_MODE!r} session, not {self.session_mode!r}"
            )
        if self.reference_space not in REFERENCE_SPACES:
            raise SessionError(
                f"reference space {self.reference_space!r} is not one of {list(REFERENCE_SPACES)}"
            )
        if self.pose_space not in POSE_SPACES:
            raise SessionError(f"pose space {self.pose_space!r} is not one of {list(POSE_SPACES)}")


class ImmersiveArSession:
    """A configured immersive-ar session, resolved against a set of input sources.

    `begin` is the offline session start: it logs every source's profiles, resolves
    each active arm's controller layout by the fallback chain, and enforces that all
    arms the mode is active on are present. It never opens the live XR session.
    """

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._resolved: dict[Handedness, ProfileResolution] = {}
        self._logged_profiles: dict[Handedness, tuple[str, ...]] = {}
        self._active = False

    @property
    def config(self) -> SessionConfig:
        """The session configuration."""
        return self._config

    @property
    def is_active(self) -> bool:
        """Whether the session has begun over a valid set of input sources."""
        return self._active

    @property
    def logged_profiles(self) -> dict[Handedness, tuple[str, ...]]:
        """The full profiles array logged for each input source at begin (⑤)."""
        return dict(self._logged_profiles)

    def begin(self, input_sources: Sequence[InputSource]) -> None:
        """Begin the session over the supplied input sources.

        Every source's full profiles array is logged (⑤). Each arm the mode is active
        on must be present and resolve by the fallback chain or the xr-standard
        mapping; a single-arm mode requires exactly its one arm, which is what admits
        one-controller operation (④).

        Args:
            input_sources: The WebXR input sources reported by the session.

        Raises:
            SessionError: If an active arm has no source, or a duplicate arm is
                supplied.
            ProfileResolutionError: If an active arm's controller resolves by neither
                the chain nor the standard mapping (raised from `resolve_layout`).
        """
        self._reset()
        by_side = self._index_by_side(input_sources)

        for side in self._config.mode.active_sides:
            source = by_side.get(side)
            if source is None:
                raise SessionError(
                    f"mode {self._config.mode.value!r} needs a {side.value!r} input source; "
                    f"present sides are {sorted(s.value for s in by_side)}"
                )
            self._resolved[side] = resolve_layout(source.profiles, source.gamepad.mapping)

        self._active = True

    def resolution_for(self, handedness: Handedness) -> ProfileResolution:
        """Return the resolved controller layout for an active arm.

        Args:
            handedness: The arm to look up.

        Returns:
            (ProfileResolution) The resolution recorded at begin.

        Raises:
            SessionError: If the session has not begun, or the arm is not active.
        """
        if not self._active:
            raise SessionError("session has not begun; call begin(input_sources) first")
        resolution = self._resolved.get(handedness)
        if resolution is None:
            raise SessionError(
                f"{handedness.value!r} is not an active arm of mode {self._config.mode.value!r}"
            )
        return resolution

    def _reset(self) -> None:
        """Clear resolution state so `begin` is idempotent on re-entry."""
        self._resolved = {}
        self._logged_profiles = {}
        self._active = False

    def _index_by_side(self, input_sources: Sequence[InputSource]) -> dict[Handedness, InputSource]:
        """Log every source's profiles (⑤) and index sources by arm, rejecting dupes.

        Args:
            input_sources: The WebXR input sources.

        Returns:
            (dict[Handedness, InputSource]) One source per arm.

        Raises:
            SessionError: If two sources claim the same arm.
        """
        by_side: dict[Handedness, InputSource] = {}
        for source in input_sources:
            profiles = tuple(source.profiles)
            self._logged_profiles[source.handedness] = profiles
            _LOGGER.info(
                "webxr inputSource handedness=%s profiles=%s", source.handedness.value, profiles
            )
            if source.handedness in by_side:
                raise SessionError(f"duplicate input source for arm {source.handedness.value!r}")
            by_side[source.handedness] = source
        return by_side
