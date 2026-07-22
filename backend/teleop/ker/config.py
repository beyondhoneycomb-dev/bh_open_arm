"""LeRobot plugin config for the KER teleoperator (WP-3B-14, FR-TEL-062).

Registers the `openarm_ker` teleoperator choice so `--teleop.type=openarm_ker`
selects it — the same third-party-plugin mechanism the VR teleoperator and the dummy
leader use, so LeRobot proper is never forked (05 §2.3). The USB identity defaults
are consumed from the frozen CTR-TEL contract, not restated.
"""

from __future__ import annotations

from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig

from contracts.teleop import KER_TELEOP_TYPE, KER_USB_PID, KER_USB_VID


@TeleoperatorConfig.register_subclass(KER_TELEOP_TYPE)
@dataclass
class OpenArmKERConfig(TeleoperatorConfig):
    """Config for the KER leader.

    Attributes:
        bimanual: Whether the action is the 16-channel bimanual keyset or the
            8-channel single-arm one.
        use_velocity_and_torque: Whether the paired follower records velocity and
            torque; when true the action keyset carries the honest-zero `.vel`/
            `.torque` columns (FR-TEL-064). This must match the paired follower's
            switch, or the record loop raises a KeyError indexing a missing key
            (05 §2.5) — hence a single switch, never a per-channel one.
        usb_vid: USB vendor id, defaulting to the contract's Espressif id (0x303A).
        usb_pid: USB product id, defaulting to the contract's KER id (0x4002).
    """

    bimanual: bool = True
    use_velocity_and_torque: bool = True
    usb_vid: int = KER_USB_VID
    usb_pid: int = KER_USB_PID
