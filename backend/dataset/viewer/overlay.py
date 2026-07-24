"""Joint-limit and torque-`tmax` overlays with near/saturation highlighting.

`FR-DAT-013`: the viewer overlays joint limits on position trajectories and each
motor's `tmax` on torque series, and highlights the near and saturated regions.
Two limit sources are distinguished, because they are different quantities: the
*mechanical* limit is the v2 URDF canon, and the *soft clamp* is the follower
config's software bound. A channel may carry both, labelled apart, so an operator
is never shown a soft clamp as if it were the mechanical stop.

The overlay values themselves (per-joint limits, per-motor `tmax`) come from the
robot description and follower config, which are not part of a dataset — the
caller supplies an `OverlaySpec`, and this module computes the highlight masks
against a channel's series. The three Damiao `tmax` values are recorded here as
the documented reference (`FR-DAT-013`), for a caller assembling a torque overlay.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray

from backend.dataset.viewer.constants import SATURATION_NEAR_FRACTION

# The Damiao motor torque limits in Nm (`FR-DAT-013`: DM8009 54 / DM4340 28 /
# DM4310 10). A reference for a caller building a torque overlay; the mapping from
# a joint to its motor model is robot config the viewer does not own.
DAMIAO_TMAX_NM = {
    "DM8009": 54.0,
    "DM4340": 28.0,
    "DM4310": 10.0,
}


class LimitKind(Enum):
    """Which kind of bound a limit band represents.

    MECHANICAL is the v2 URDF hard stop (the machine limit); SOFT_CLAMP is the
    follower config's software bound. They are shown together but never conflated.
    """

    MECHANICAL = "mechanical"
    SOFT_CLAMP = "soft_clamp"


@dataclass(frozen=True)
class LimitBand:
    """One bounded region a channel is checked against.

    Attributes:
        lower: The band's lower bound (channel units).
        upper: The band's upper bound (channel units).
        kind: Whether this is the mechanical limit or a soft clamp.
    """

    lower: float
    upper: float
    kind: LimitKind

    def __post_init__(self) -> None:
        """Reject a degenerate band whose bounds are inverted or equal."""
        if self.upper <= self.lower:
            raise ValueError(f"limit band upper {self.upper} must exceed lower {self.lower}")


def torque_band(tmax: float) -> LimitBand:
    """Build the symmetric mechanical torque band `[-tmax, +tmax]` for a motor.

    Args:
        tmax: The motor's torque limit in Nm.

    Returns:
        (LimitBand) The symmetric mechanical band.
    """
    return LimitBand(lower=-abs(tmax), upper=abs(tmax), kind=LimitKind.MECHANICAL)


@dataclass(frozen=True)
class BandAnnotation:
    """A channel's per-frame proximity to one limit band.

    Attributes:
        kind: The band this annotation is for (mechanical or soft clamp).
        near_mask: True where the sample is near the bound but not past it.
        saturated_mask: True where the sample is at or beyond the bound.
    """

    kind: LimitKind
    near_mask: NDArray[np.bool_]
    saturated_mask: NDArray[np.bool_]

    def saturated_frames(self) -> tuple[int, ...]:
        """Return the frame indices at or beyond the bound."""
        return tuple(int(i) for i in np.flatnonzero(self.saturated_mask))

    def near_frames(self) -> tuple[int, ...]:
        """Return the frame indices near but not past the bound."""
        return tuple(int(i) for i in np.flatnonzero(self.near_mask))


@dataclass(frozen=True)
class ChannelAnnotation:
    """A channel's proximity annotations across all its limit bands.

    Attributes:
        channel: The channel name the annotation is for.
        bands: One `BandAnnotation` per band supplied for the channel.
    """

    channel: str
    bands: tuple[BandAnnotation, ...]


def annotate_channel(
    series: NDArray[np.float64],
    bands: tuple[LimitBand, ...],
    near_fraction: float = SATURATION_NEAR_FRACTION,
) -> ChannelAnnotation:
    """Highlight where a channel is near or past each of its limit bands.

    A sample is *saturated* when its distance from the band centre reaches the
    half-span (at or beyond a bound), and *near* when that distance is at least
    `near_fraction` of the half-span but not yet saturated. The centre/half-span
    form treats a symmetric torque band and an asymmetric joint band uniformly.

    Args:
        series: The channel's per-frame values.
        bands: The limit bands to check the channel against.
        near_fraction: The fraction of the half-span at which "near" begins.

    Returns:
        (ChannelAnnotation) One `BandAnnotation` per band, in the given order.
    """
    annotations: list[BandAnnotation] = []
    for band in bands:
        centre = (band.upper + band.lower) / 2.0
        half_span = (band.upper - band.lower) / 2.0
        distance = np.abs(series - centre)
        saturated = distance >= half_span
        near = (distance >= near_fraction * half_span) & ~saturated
        annotations.append(BandAnnotation(kind=band.kind, near_mask=near, saturated_mask=saturated))
    return ChannelAnnotation(channel="", bands=tuple(annotations))


# The overlay a caller supplies: a channel name to the bands it is checked against.
OverlaySpec = dict[str, tuple[LimitBand, ...]]


def annotate(
    series_by_channel: dict[str, NDArray[np.float64]], spec: OverlaySpec
) -> dict[str, ChannelAnnotation]:
    """Annotate every channel that both has a series and a limit spec.

    A channel in the spec with no series is skipped, and a channel with a series
    but no spec is left un-annotated — the overlay is only drawn where limits are
    actually declared.

    Args:
        series_by_channel: Per-channel value arrays (e.g. from `EpisodeSignals`).
        spec: Per-channel limit bands the caller declares.

    Returns:
        (dict[str, ChannelAnnotation]) The annotations, keyed by channel name.
    """
    result: dict[str, ChannelAnnotation] = {}
    for channel, bands in spec.items():
        series = series_by_channel.get(channel)
        if series is None:
            continue
        annotation = annotate_channel(series, bands)
        result[channel] = ChannelAnnotation(channel=channel, bands=annotation.bands)
    return result
