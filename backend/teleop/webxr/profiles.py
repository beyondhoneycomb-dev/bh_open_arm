"""Controller profile resolution by fallback chain, never a whitelist (WP-3B-08 ①).

The upstream defect this WP exists to fix: `ar.js` reads the trigger only when the
first reported profile string is an EXACT member of a small set, and `main.py` then
gates pose publication on `if pose in response and trigger in response`. A headset
whose profile string is outside that set has its trigger dropped, and with the
trigger dropped the pose is never published — the whole teleop path goes dark
(`05` §2.7 ⓐ, `FR-TEL-017`). The Quest 3S's reported profile string is unconfirmed
(`05` §5 U-6), so an exact-string whitelist is a live outage risk, not a hypothetical.

The fix, and the shape of this module, is: resolve a controller by the fallback
CHAIN or by whether its gamepad reports the `xr-standard` mapping. Both branches
yield the one `xr-standard` layout (`buttons[0]`=trigger, `buttons[1]`=squeeze,
`axes[2]/[3]`=thumbstick), because every profile in the chain maps to it. The
load-bearing property is what is ABSENT: there is no code path that rejects a
controller merely because its profile string is unknown. An unknown profile with an
`xr-standard` gamepad resolves; resolution fails only when a controller is neither in
the chain nor reports the standard mapping, which is the startup-refusal the spec
sanctions (`05` §2.7 config table "컨트롤러 프로필 불일치" → 기동 거부, S0).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from backend.teleop.webxr.constants import (
    FALLBACK_PROFILE_CHAIN,
    XR_STANDARD_MAPPING,
    XR_STANDARD_PRIMARY_FACE_BUTTON_INDEX,
    XR_STANDARD_SECONDARY_FACE_BUTTON_INDEX,
    XR_STANDARD_SQUEEZE_BUTTON_INDEX,
    XR_STANDARD_THUMBSTICK_X_AXIS_INDEX,
    XR_STANDARD_THUMBSTICK_Y_AXIS_INDEX,
    XR_STANDARD_TRIGGER_BUTTON_INDEX,
)


class ProfileResolutionError(ValueError):
    """Raised when a controller matches neither the fallback chain nor xr-standard."""


class ResolvedVia(StrEnum):
    """How a controller layout was resolved — the provenance of a match.

    `CHAIN` means one of the controller's reported profile strings is a known
    fallback-chain entry. `XR_STANDARD` means no reported profile was known but the
    gamepad reports the `xr-standard` mapping — the branch that admits an unknown
    headset. Both are valid resolutions; the distinction is kept so a caller (and a
    test) can prove an unknown profile was admitted by the mapping, not the chain.
    """

    CHAIN = "chain"
    XR_STANDARD = "xr_standard"


@dataclass(frozen=True)
class ControllerLayout:
    """The `xr-standard` button/axis index layout of a resolved controller.

    Every profile in the fallback chain maps to this single layout, so the layout is
    a constant of the standard mapping rather than per-profile data. It is carried as
    a value so the gamepad reader indexes by a named role, never a bare integer.

    Attributes:
        trigger_button_index: Index of the trigger button (`buttons[0]`).
        squeeze_button_index: Index of the squeeze/grip button (`buttons[1]`).
        primary_face_button_index: Index of the A/X face button (`buttons[4]`).
        secondary_face_button_index: Index of the B/Y face button (`buttons[5]`).
        thumbstick_x_axis_index: Index of the thumbstick x axis (`axes[2]`).
        thumbstick_y_axis_index: Index of the thumbstick y axis (`axes[3]`).
    """

    trigger_button_index: int
    squeeze_button_index: int
    primary_face_button_index: int
    secondary_face_button_index: int
    thumbstick_x_axis_index: int
    thumbstick_y_axis_index: int


# The one layout every chain profile and the `xr-standard` mapping resolve to
# (`05` §2.7 registry note). Named once so a resolution returns the shared layout
# rather than reconstructing the indices per call site.
XR_STANDARD_LAYOUT = ControllerLayout(
    trigger_button_index=XR_STANDARD_TRIGGER_BUTTON_INDEX,
    squeeze_button_index=XR_STANDARD_SQUEEZE_BUTTON_INDEX,
    primary_face_button_index=XR_STANDARD_PRIMARY_FACE_BUTTON_INDEX,
    secondary_face_button_index=XR_STANDARD_SECONDARY_FACE_BUTTON_INDEX,
    thumbstick_x_axis_index=XR_STANDARD_THUMBSTICK_X_AXIS_INDEX,
    thumbstick_y_axis_index=XR_STANDARD_THUMBSTICK_Y_AXIS_INDEX,
)


@dataclass(frozen=True)
class ProfileResolution:
    """The outcome of resolving one input source's controller.

    Attributes:
        layout: The resolved `xr-standard` layout.
        matched_profile: The profile string that matched, or the `xr-standard`
            mapping token when resolution came from the mapping rather than the chain.
        via: Whether the chain or the standard mapping resolved the controller.
    """

    layout: ControllerLayout
    matched_profile: str
    via: ResolvedVia


def chain_match(profiles: Sequence[str]) -> str | None:
    """Return the first reported profile that is a known fallback-chain entry.

    The controller's `profiles` array is ordered most-specific to least-specific
    (WebXR contract), and the chain is scanned in the controller's own order so the
    most specific known profile wins.

    Args:
        profiles: The `inputSource.profiles` strings, in the controller's order.

    Returns:
        (str | None) The first profile present in the fallback chain, or None.
    """
    chain = frozenset(FALLBACK_PROFILE_CHAIN)
    for profile in profiles:
        if profile in chain:
            return profile
    return None


def resolve_layout(profiles: Sequence[str], mapping: str) -> ProfileResolution:
    """Resolve a controller layout by the fallback chain or the `xr-standard` mapping.

    This is the acceptance-① surface. There is deliberately no branch that rejects a
    controller for having an unknown profile string: an unknown profile whose gamepad
    reports the `xr-standard` mapping resolves via `ResolvedVia.XR_STANDARD`.
    Resolution fails only when the controller is in neither the chain nor the standard
    mapping — the sanctioned startup refusal, not an unknown-headset lockout.

    Args:
        profiles: The `inputSource.profiles` strings, in the controller's order.
        mapping: The controller gamepad's `mapping` string.

    Returns:
        (ProfileResolution) The resolved layout and how it was resolved.

    Raises:
        ProfileResolutionError: When neither the chain nor the standard mapping matches.
    """
    matched = chain_match(profiles)
    if matched is not None:
        return ProfileResolution(
            layout=XR_STANDARD_LAYOUT, matched_profile=matched, via=ResolvedVia.CHAIN
        )
    if mapping == XR_STANDARD_MAPPING:
        return ProfileResolution(
            layout=XR_STANDARD_LAYOUT,
            matched_profile=XR_STANDARD_MAPPING,
            via=ResolvedVia.XR_STANDARD,
        )
    raise ProfileResolutionError(
        f"controller resolves via neither the fallback chain nor the {XR_STANDARD_MAPPING!r} "
        f"mapping (profiles={list(profiles)!r}, mapping={mapping!r}); startup is refused"
    )


def is_resolvable(profiles: Sequence[str], mapping: str) -> bool:
    """Report whether a controller resolves without raising.

    Args:
        profiles: The `inputSource.profiles` strings, in the controller's order.
        mapping: The controller gamepad's `mapping` string.

    Returns:
        (bool) True when `resolve_layout` would succeed.
    """
    return chain_match(profiles) is not None or mapping == XR_STANDARD_MAPPING
