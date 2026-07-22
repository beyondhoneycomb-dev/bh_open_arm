"""The motor ERR-nibble decoder at the actuation boundary (`WP-1-03`, acceptance ⑰).

The Damiao feedback frame carries an ERR nibble the upstream `MotorState` discards
(`14` FR-OPS-018). `contracts.errors.damiao_map` already extracts it and maps the
known nibbles to `OA-MOT` codes from the frozen CTR-ERR@v1 registry. This module is
the thin actuation-side wrapper that adds the one thing the gateway needs and the
raw map deliberately does not enforce: an **unknown** nibble is an explicit error,
never a silent "not a fault".

`parse_motor_err` maps every known nibble — the disabled baseline, the Enable normal
state, and the seven fault nibbles `8..E` — and returns `is_error=False` for a
nibble it does not recognise. That is the correct contract for a diagnostic reader,
but at the safety gateway a status byte whose high nibble is outside the known set is
not "healthy"; it is a frame the decoder cannot vouch for, and treating it as healthy
is exactly the silent-ignore acceptance ⑰ forbids. So `decode_motor_err` raises
`UnknownErrNibbleError` on an unrecognised nibble rather than passing it through.
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.errors.constants import DAMIAO_ENABLE_NIBBLE
from contracts.errors.damiao_map import NIBBLE_TO_CODE, extract_err_nibble


class UnknownErrNibbleError(ValueError):
    """Raised when a feedback status byte carries an ERR nibble outside the known set.

    Attributes:
        nibble: The unrecognised nibble, as an upper-hex character.
    """

    def __init__(self, nibble: str) -> None:
        """Build the error, naming the offending nibble.

        Args:
            nibble: The unrecognised ERR nibble.
        """
        super().__init__(
            f"unknown motor ERR nibble {nibble!r}: not the Enable state and not one of the "
            f"registered OA-MOT fault nibbles; a status the decoder cannot vouch for is an "
            f"explicit error, never a silent 'healthy' (14 §2.4)"
        )
        self.nibble = nibble


@dataclass(frozen=True)
class DecodedMotorErr:
    """A decoded feedback ERR nibble the gateway can act on.

    Attributes:
        nibble: The raw ERR nibble, upper-hex.
        code: The `OA-MOT` code it maps to, or None for the Enable normal state.
        is_fault: True when the nibble denotes a fault rather than a normal state.
    """

    nibble: str
    code: str | None
    is_fault: bool


def decode_motor_err(status_byte: int) -> DecodedMotorErr:
    """Decode a Damiao feedback status byte, raising on an unknown nibble.

    Args:
        status_byte: The status byte from a Damiao feedback frame.

    Returns:
        (DecodedMotorErr) The nibble, its `OA-MOT` code (None for Enable), and
        whether it is a fault.

    Raises:
        UnknownErrNibbleError: When the ERR nibble is neither the Enable state nor a
            registered fault nibble — the unknown case acceptance ⑰ forbids ignoring.
    """
    nibble = extract_err_nibble(status_byte)
    if int(nibble, 16) == DAMIAO_ENABLE_NIBBLE:
        return DecodedMotorErr(nibble=nibble, code=None, is_fault=False)
    code = NIBBLE_TO_CODE.get(nibble)
    if code is None:
        raise UnknownErrNibbleError(nibble)
    # OA-MOT-000 is the disabled baseline state, mapped but not a fault.
    is_fault = code != "OA-MOT-000"
    return DecodedMotorErr(nibble=nibble, code=code, is_fault=is_fault)
