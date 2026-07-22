"""A stop path that cuts torque — the acceptance-⑬ violation (`04` NFR-MAN-002 forbids it).

Data, not logic. The stop path must be a single MIT hold frame, never a torque cut:
cutting torque blocks ~8 ms single / ~16 ms bimanual and drops a brakeless arm. This
file names `disable_torque` on a stop path so `find_disable_torque` has a real
violation to catch and prove it does not pass vacuously.
"""

from __future__ import annotations


class TorqueCuttingStop:
    """A stop that cuts torque instead of holding — the forbidden shape."""

    def stop(self) -> None:
        """Cut torque on stop — the symbol the scan must flag."""
        self.bus.disable_torque()  # type: ignore[attr-defined]
