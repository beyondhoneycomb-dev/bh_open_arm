"""The CG-2B-08c code-level lock: collision detection cannot be enabled under path B.

FR-SAF-030 forces the detection method to DISABLED until the v2 friction model is identified.
Path B is precisely the state where it is not, so the lock is unconditional: `enabled` is a
constant False with no setter, and every enable path raises `DetectionLockError`. There is
deliberately no attribute a caller can flip. 02b §2.4 ("경로 B 존재" cost) names this lock the
only defense against the standing false-positive/false-negative risk of computing residuals on an
unidentified model, so a bypass would defeat the whole work package.
"""

from __future__ import annotations

from backend.pathb.constants import DETECTION_METHOD_DISABLED
from backend.pathb.errors import DetectionLockError


class DetectionLock:
    """Collision detection, held DISABLED for the lifetime of a path-B session.

    Ownership/threading: one lock belongs to one `PathBBootstrap` and carries no mutable enable
    state, so it is safe to read from any thread — there is nothing to synchronize because nothing
    can change it.
    """

    @property
    def enabled(self) -> bool:
        """Whether collision detection is enabled. Always False under path B (FR-SAF-030)."""
        return False

    @property
    def method(self) -> str:
        """The forced detection method — always `DISABLED` (FR-SAF-030)."""
        return DETECTION_METHOD_DISABLED

    def enable(self) -> None:
        """Refuse to enable collision detection.

        Raises:
            DetectionLockError: Always. Enabling detection under path B is the action FR-SAF-030
                forbids until the v2 friction model is identified.
        """
        raise DetectionLockError(
            "collision detection cannot be enabled under path B: the v2 friction model is "
            "unidentified (FR-SAF-030); enable is blocked until PG-FRIC-001 passes"
        )

    def set_method(self, method: str) -> None:
        """Accept only `DISABLED`; refuse every activating detection method.

        Args:
            method: The requested detection method.

        Raises:
            DetectionLockError: If `method` is anything other than `DISABLED`.
        """
        if method != DETECTION_METHOD_DISABLED:
            raise DetectionLockError(
                f"detection method {method!r} is refused under path B: only "
                f"{DETECTION_METHOD_DISABLED!r} is permitted until PG-FRIC-001 passes (FR-SAF-030)"
            )
