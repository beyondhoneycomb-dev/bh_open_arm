"""The txqueuelen setup artifact (`01` FR-SYS-011) — guidance, never execution.

FR-SYS-011 (priority S) asks that the setup step raise `txqueuelen` above the kernel
default of 10 to a recommended 1000; neither LeRobot nor the enactic scripts do this.
Because FR-SYS-006 forbids code from setting the link, this artifact is *documentation*
the operator runs — the `ip link set … txqueuelen` lines it holds are strings the code
returns, never commands it executes. The acceptance (⑥) is only that the recommended
value is present in the artifact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.can.link.constants import DEFAULT_TXQUEUELEN, RECOMMENDED_TXQUEUELEN


@dataclass(frozen=True)
class SetupArtifact:
    """The operator-facing setup guidance for CAN link queue length.

    Attributes:
        ifaces: Channels the guidance covers.
        recommended_txqueuelen: The FR-SYS-011 recommended value (1000).
        default_txqueuelen: The kernel default the recommendation replaces (10).
        commands: Per-channel `ip link set … txqueuelen` guidance strings. These are
            data for the operator to run; the backend never executes them.
    """

    ifaces: tuple[str, ...]
    recommended_txqueuelen: int
    default_txqueuelen: int
    commands: tuple[str, ...]

    def render(self) -> str:
        """Render the artifact as an operator-readable document.

        Returns:
            (str) A text block naming the recommended queue length and the exact
            per-channel commands to raise it.
        """
        header = (
            f"CAN txqueuelen setup (01 FR-SYS-011): raise from the kernel default "
            f"{self.default_txqueuelen} to the recommended {self.recommended_txqueuelen}. "
            f"Run these yourself; the backend does not set the link."
        )
        return "\n".join([header, *(f"  {command}" for command in self.commands)])


def build_setup_artifact(ifaces: Sequence[str]) -> SetupArtifact:
    """Build the txqueuelen setup artifact for a set of channels.

    Args:
        ifaces: Channels to generate guidance for.

    Returns:
        (SetupArtifact) The recommended value and the per-channel guidance commands.
    """
    commands = tuple(f"ip link set {iface} txqueuelen {RECOMMENDED_TXQUEUELEN}" for iface in ifaces)
    return SetupArtifact(
        ifaces=tuple(ifaces),
        recommended_txqueuelen=RECOMMENDED_TXQUEUELEN,
        default_txqueuelen=DEFAULT_TXQUEUELEN,
        commands=commands,
    )
