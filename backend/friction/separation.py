"""Residual-separation statistics: is the fit residual free of gravity, Coriolis and inertia?

Acceptance ① requires the friction fit to converge *and* its residual to be separated from the
gravity and inertia terms, shown by statistics. §2.0 is why: if the gravity model fed to the
fit is wrong (the classic v1-convention shoulder error), the friction fit silently absorbs that
error and "no error is raised". The tell is a lingering correlation — the post-fit residual
still tracks the model signal it should be independent of.

For each joint this reports the correlation of the post-fit residual with each of the three
rigid-body signals and the fraction of the friction-band variance the fit explained. A fit is
`separated` when no model-signal correlation exceeds `SEPARATION_MAX_ABS_CORR` and the fit
explains at least `SEPARATION_MIN_R2` of that variance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.friction.constants import SEPARATION_MAX_ABS_CORR, SEPARATION_MIN_R2
from backend.friction.identify import IdentificationResult

# Below this standard deviation a signal is treated as constant, and correlation with it is
# undefined; it is reported as zero because a constant signal carries no structure the residual
# could be leaking into.
_DEGENERATE_STD = 1.0e-12


@dataclass(frozen=True)
class SeparationStat:
    """One joint's residual-separation evidence.

    Attributes:
        joint_index: Zero-based arm joint index (0 = joint1).
        corr_gravity: Correlation of the post-fit residual with the gravity signal.
        corr_coriolis: Correlation of the post-fit residual with the Coriolis signal.
        corr_inertia: Correlation of the post-fit residual with the inertia signal.
        r2: Fraction of the friction-residual variance the fit explained (`1 - var(e)/var(y)`).
        separated: Whether every model-signal correlation and the `r2` clear their thresholds.
    """

    joint_index: int
    corr_gravity: float
    corr_coriolis: float
    corr_inertia: float
    r2: float
    separated: bool

    def max_abs_corr(self) -> float:
        """Return the largest absolute model-signal correlation."""
        return max(abs(self.corr_gravity), abs(self.corr_coriolis), abs(self.corr_inertia))


def _safe_corr(residual: NDArray[np.float64], signal: NDArray[np.float64]) -> float:
    """Return the Pearson correlation of two series, or 0.0 when either is constant.

    Args:
        residual: The post-fit residual series.
        signal: A rigid-body model signal series.

    Returns:
        (float) The correlation, or 0.0 for a degenerate (constant) input.
    """
    if residual.std() < _DEGENERATE_STD or signal.std() < _DEGENERATE_STD:
        return 0.0
    return float(np.corrcoef(residual, signal)[0, 1])


def _r2(post_fit: NDArray[np.float64], target: NDArray[np.float64]) -> float:
    """Return the fraction of `target` variance the fit explained.

    Args:
        post_fit: The residual left after subtracting the fitted friction.
        target: The friction residual the fit tried to explain.

    Returns:
        (float) `1 - var(post_fit)/var(target)`, or 0.0 when the target is constant.
    """
    target_var = float(np.var(target))
    if target_var < _DEGENERATE_STD:
        return 0.0
    return 1.0 - float(np.var(post_fit)) / target_var


def separation_stats(result: IdentificationResult) -> tuple[SeparationStat, ...]:
    """Compute per-joint separation statistics for a whole-arm identification.

    Args:
        result: The identification whose residuals to test.

    Returns:
        (tuple[SeparationStat, ...]) One statistic per joint, joint1..joint7 order.
    """
    components = result.components
    stats: list[SeparationStat] = []
    for fit in result.fits:
        joint = fit.joint_index
        target = result.friction_residual[:, joint]
        fitted = fit.params.tau(result.velocity[:, joint])
        post_fit = target - fitted
        corr_gravity = _safe_corr(post_fit, components.gravity[:, joint])
        corr_coriolis = _safe_corr(post_fit, components.coriolis[:, joint])
        corr_inertia = _safe_corr(post_fit, components.inertia[:, joint])
        r2 = _r2(post_fit, target)
        separated = (
            max(abs(corr_gravity), abs(corr_coriolis), abs(corr_inertia)) <= SEPARATION_MAX_ABS_CORR
            and r2 >= SEPARATION_MIN_R2
        )
        stats.append(
            SeparationStat(
                joint_index=joint,
                corr_gravity=corr_gravity,
                corr_coriolis=corr_coriolis,
                corr_inertia=corr_inertia,
                r2=r2,
                separated=separated,
            )
        )
    return tuple(stats)


def format_separation_table(stats: Sequence[SeparationStat]) -> str:
    """Render the separation statistics as a fixed-width text table.

    Args:
        stats: The per-joint statistics.

    Returns:
        (str) A table with a header, one row per joint, and a separated/total footer.
    """
    header = (
        f"{'joint':>6} {'corr(g)':>10} {'corr(Cqd)':>10} {'corr(Mqdd)':>11} "
        f"{'R^2':>8} {'separated':>10}"
    )
    lines = [header, "-" * len(header)]
    for stat in stats:
        lines.append(
            f"{stat.joint_index + 1:>6} {stat.corr_gravity:>10.4f} {stat.corr_coriolis:>10.4f} "
            f"{stat.corr_inertia:>11.4f} {stat.r2:>8.4f} {str(stat.separated):>10}"
        )
    passed = sum(1 for stat in stats if stat.separated)
    lines.append(f"{'total':>6} separated {passed}/{len(stats)}")
    return "\n".join(lines)
