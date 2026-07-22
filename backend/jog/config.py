"""Named parameters of the joint jog producer (`WP-2A-01`).

Every literal the jog trajectory logic depends on is named here rather than buried
at a call site, so the one place a jog default is decided is the one place it is
read. None of these is a production loop-rate claim: the scheduler's tick rate is
`PG-RT-001a` (`WP-0A-01`, deliberately unfixed), and these are the *producer's*
own publish-cadence and step vocabulary, independent of how fast the scheduler
consumes them through the latest-wins mailbox.
"""

from __future__ import annotations

# The step-size vocabulary a step-mode jog offers, in degrees (`04` FR-MAN-010).
# The spec fixes these four as the minimum offered set; a step outside the set is
# rejected by `addressing.validate_step_size` so the vocabulary stays meaningful.
STEP_SIZES_DEG: tuple[float, ...] = (0.1, 0.5, 1.0, 5.0)

# Reference interpolation cadence and step duration (`04` FR-MAN-010 cites
# `openarm_driver.smooth_move`: `np.linspace`, 50 Hz over 2 s). The emitted frame
# count of one step is `round(hz * duration)`, so these two set how many
# interpolated waypoints a single step becomes.
DEFAULT_INTERPOLATION_HZ: float = 50.0
DEFAULT_STEP_DURATION_SEC: float = 2.0
