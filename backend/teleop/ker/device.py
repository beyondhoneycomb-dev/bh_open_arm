"""KER USB encoder reader — joint angles only, no CAN, no IK (WP-3B-14, FR-TEL-063).

The KER is a motorless leader arm whose magnetic joint encoders enumerate over USB
(Espressif ESP32-S3, VID 0x303A / PID 0x4002) and stream joint angles in degrees; the
upstream `openarm_ker` package (`ker_stream.py`) is the wrapped source (05 §2.12).
This reader consumes ZERO CAN channels — it opens a USB endpoint, never a socket —
and performs NO inverse kinematics: the angles it reads ARE the command.

`pyusb` and `openarm_ker` are optional and absent on the dev desktop, so `UsbKerDevice`
raises `KerDeviceUnavailableError` at connect() rather than fabricating a read — the mock
is the ONLY offline source and is never the default (never fake a real read). Real
USB I/O is deferred and re-verified on hardware through `backend.teleop.ker.reverify`.
"""

from __future__ import annotations

import abc
import importlib
import importlib.util
import math
from collections.abc import Sequence
from dataclasses import dataclass

from contracts.teleop import TeleopValidity

# The upstream stream module and the USB backend it needs. Named so both the guard
# and its failure message reference one spelling.
_PYUSB_MODULE = "usb.core"
_OPENARM_KER_MODULE = "openarm_ker.ker_stream"


class KerDeviceUnavailableError(RuntimeError):
    """Raised when the real KER USB device cannot be opened (deps or device absent)."""


@dataclass(frozen=True)
class KerReading:
    """One KER encoder frame: joint angles and their tracking validity.

    Attributes:
        joint_angles_deg: Joint angles in degrees, in motor order — one per position
            channel of the configured keyset.
        validity: The three-level tracking validity (CTR-TEL@v1). The shared safety
            gate consumes this exactly as it does a VR sample; the KER re-implements
            none of that gate.
    """

    joint_angles_deg: tuple[float, ...]
    validity: TeleopValidity


def module_available(dotted: str) -> bool:
    """Report whether an optional module can be imported without importing it.

    Args:
        dotted: Dotted module name, e.g. `usb.core`.

    Returns:
        (bool) True when the module is installed.
    """
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def classify_joint_validity(joint_angles_deg: Sequence[float]) -> TeleopValidity:
    """Classify a raw joint frame's tracking validity from its contents.

    A non-finite angle (NaN / inf) is the KER analogue of VR's non-finite / det≈0
    pose: the frame is unusable and is marked INVALID so the shared safety gate
    discards it (05 §2.14). STALE is an age verdict the heartbeat renders downstream,
    not a property of a single frame, so a finite frame is OK here.

    Args:
        joint_angles_deg: Raw joint angles in degrees.

    Returns:
        (TeleopValidity) INVALID for a non-finite frame, OK otherwise.
    """
    if any(not math.isfinite(angle) for angle in joint_angles_deg):
        return TeleopValidity.INVALID
    return TeleopValidity.OK


class KerDevice(abc.ABC):
    """A source of KER encoder frames: connect, read, disconnect.

    Two concrete readers implement it: `UsbKerDevice` (the real, deferred USB path)
    and `MockKerDevice` (the offline synthetic source used by tests and dry runs).
    """

    @property
    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Whether the reader is currently connected."""

    @abc.abstractmethod
    def connect(self) -> None:
        """Open the reader, or raise `KerDeviceUnavailableError` when it cannot."""

    @abc.abstractmethod
    def read(self) -> KerReading:
        """Return the latest encoder frame."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Release the reader."""


class UsbKerDevice(KerDevice):
    """The real KER USB reader over `pyusb` + `openarm_ker` (deferred to hardware).

    Ownership: opens exactly one USB endpoint and holds the upstream stream handle;
    releases both on disconnect. It never opens a CAN socket (FR-TEL-063). Absent the
    optional deps or the physical device, connect() raises `KerDeviceUnavailableError`;
    read() is only reachable after a successful connect, so it never fabricates a
    frame.
    """

    def __init__(self, usb_vid: int, usb_pid: int) -> None:
        """Bind the reader to a USB vendor/product id without opening anything.

        Args:
            usb_vid: USB vendor id (the contract's Espressif id by default).
            usb_pid: USB product id (the contract's KER id by default).
        """
        self._vid = usb_vid
        self._pid = usb_pid
        self._stream: object | None = None

    @property
    def is_connected(self) -> bool:
        """Whether the USB stream handle is open."""
        return self._stream is not None

    def connect(self) -> None:
        """Open the USB endpoint and the upstream stream, or fail loudly.

        Raises:
            KerDeviceUnavailableError: When `pyusb` or `openarm_ker` is not installed, or
                no device at the configured VID/PID responds. The offline dev desktop
                takes this path — the reader never returns a fabricated frame.
        """
        if not module_available(_PYUSB_MODULE):
            raise KerDeviceUnavailableError(
                f"pyusb ({_PYUSB_MODULE}) is not installed; the KER USB reader cannot "
                f"open VID {self._vid:#06x}/PID {self._pid:#06x}"
            )
        if not module_available(_OPENARM_KER_MODULE):
            raise KerDeviceUnavailableError(
                f"openarm_ker ({_OPENARM_KER_MODULE}) is not installed; no KER stream to wrap"
            )
        usb_core = importlib.import_module(_PYUSB_MODULE)
        device = usb_core.find(idVendor=self._vid, idProduct=self._pid)
        if device is None:
            raise KerDeviceUnavailableError(
                f"no USB device at VID {self._vid:#06x}/PID {self._pid:#06x}"
            )
        ker_stream = importlib.import_module(_OPENARM_KER_MODULE)
        self._stream = ker_stream.KerStream(device)

    def read(self) -> KerReading:
        """Return the latest encoder frame from the upstream stream.

        Returns:
            (KerReading) Joint angles in degrees with their tracking validity.

        Raises:
            KerDeviceUnavailableError: If called before a successful connect.
        """
        if self._stream is None:
            raise KerDeviceUnavailableError("read() called before connect() on the USB KER reader")
        angles = tuple(float(value) for value in self._stream.read_joint_angles_deg())
        return KerReading(joint_angles_deg=angles, validity=classify_joint_validity(angles))

    def disconnect(self) -> None:
        """Release the USB stream handle."""
        stream = self._stream
        self._stream = None
        if stream is not None and hasattr(stream, "close"):
            stream.close()


class MockKerDevice(KerDevice):
    """An offline synthetic KER reader for tests and dry runs — never the default.

    It replays a fixed sequence of `KerReading`s (cycling the last), so a test can
    drive known joint angles and validities through the teleoperator without any USB
    device. It is opt-in: real deployments construct `UsbKerDevice`, which fails loudly
    on absent hardware, so synthetic angles can never be mistaken for a real read.
    """

    def __init__(self, readings: Sequence[KerReading]) -> None:
        """Bind the reader to a non-empty script of frames to replay.

        Args:
            readings: Frames to return from successive `read()` calls; the last frame
                repeats once the script is exhausted.

        Raises:
            ValueError: If the script is empty — a source with nothing to read is a
                configuration error, not a stall.
        """
        if not readings:
            raise ValueError("MockKerDevice needs at least one reading to replay")
        self._readings = tuple(readings)
        self._index = 0
        self._connected = False

    @classmethod
    def constant(
        cls, joint_angles_deg: Sequence[float], validity: TeleopValidity = TeleopValidity.OK
    ) -> MockKerDevice:
        """Build a mock that always reads one fixed frame.

        Args:
            joint_angles_deg: The joint angles in degrees to replay.
            validity: The tracking validity to report (OK by default).

        Returns:
            (MockKerDevice) A single-frame mock.
        """
        return cls([KerReading(joint_angles_deg=tuple(joint_angles_deg), validity=validity)])

    @property
    def is_connected(self) -> bool:
        """Whether the mock is connected."""
        return self._connected

    def connect(self) -> None:
        """Come online without touching any device."""
        self._connected = True

    def read(self) -> KerReading:
        """Return the next scripted frame, repeating the last once exhausted.

        Returns:
            (KerReading) The current frame.

        Raises:
            KerDeviceUnavailableError: If called while disconnected.
        """
        if not self._connected:
            raise KerDeviceUnavailableError("read() called before connect() on the mock KER reader")
        reading = self._readings[self._index]
        if self._index < len(self._readings) - 1:
            self._index += 1
        return reading

    def disconnect(self) -> None:
        """Go offline and rewind the script."""
        self._connected = False
        self._index = 0
