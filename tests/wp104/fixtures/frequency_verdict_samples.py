"""Control shapes for the NORM-008 scanner — the ones it must flag, the ones it must not.

A scanner that cannot fire is trusted for nothing, and one that fires on everything is
worse than none, so both halves are pinned here rather than only the first. The `*_shaped`
functions cover every verdict sink, and the `raise`, `gate_state`, `filter` and
`verdict_field` sinks are covered in each statement form they accept — a sink tested in one
form only can lose the other form to a deletion no test notices. The `hoisted_*` shapes
carry that further: binding the condition to a local empties every sink expression at once,
so each sink is covered with the bar spelled inline and with it reached through a name.

The rest are modelled on live code the ruling leaves alone: a malformed-request guard
(`backend/loadtest/publish_rate.py:56`), a cap refusal that returns rather than judges
(`:60`), band scoping (`BandPoint.in_main_path`), the band published as a label beside the
point (`BandPoint.as_record`), and a plain measurement.

Nothing here is called. These functions exist to be parsed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

CAP_HZ = 60.0
REQUIRED_HZ = 100.0
ON_TIME_RATIO = 0.95
BAND_LOW_HZ = 30.0
BAND_HIGH_HZ = 250.0

GATE_STATE_PASS = "PASS"
GATE_STATE_FAIL = "FAIL"

TOO_FAST_EXIT_CODE = 2


class TargetTooFastError(ValueError):
    """A requested target frequency was refused for being above a cap."""


@dataclass(frozen=True)
class ProvisionalPermit:
    """A published permit record; `permit_keyword_shaped` builds its field by keyword.

    Attributes:
        is_exit_permit: Whether the measurement permits the wave to proceed.
    """

    is_exit_permit: bool


def enforce_target_shaped(target_hz: float) -> None:
    """Sink `raise`: a frequency above a bar aborts the caller."""
    if target_hz > CAP_HZ:
        raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def nested_raise_shaped(target_hz: float, strict: bool) -> None:
    """Sink `raise`, wrapped one level deeper — the same bar, reached through a branch."""
    if target_hz > CAP_HZ:  # noqa: SIM102 — the nesting is the evasion under test
        if strict:
            raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def else_branch_raise_shaped(target_hz: float) -> None:
    """Sink `raise` on the `else` side — the bar inverted, the abort unchanged."""
    if target_hz <= CAP_HZ:
        return
    else:  # noqa: RET505 — the else branch is the evasion under test
        raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def while_raise_shaped(target_hz: float) -> None:
    """Sink `raise` on a `while` guard — the same bar, spelled as a loop test."""
    while target_hz > CAP_HZ:
        raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def _abort_too_fast(target_hz: float) -> None:
    """The abort `helper_abort_shaped` reaches through a call instead of spelling out."""
    raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def helper_abort_shaped(target_hz: float) -> None:
    """Sink `raise` one call away — the branch itself contains no `raise` keyword."""
    if target_hz > CAP_HZ:
        _abort_too_fast(target_hz)


def exit_shaped(target_hz: float) -> None:
    """Sink `raise` with no exception at all — the process ends instead of unwinding."""
    if target_hz > CAP_HZ:
        sys.exit(TOO_FAST_EXIT_CODE)


def hoisted_raise_shaped(target_hz: float) -> None:
    """Sink `raise` with the bar bound to a local first — the sink expression is a name."""
    too_fast = target_hz > CAP_HZ
    if too_fast:
        raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def rehoisted_raise_shaped(target_hz: float) -> None:
    """Sink `raise` with the bar hoisted twice — one binding standing in for another."""
    too_fast = target_hz > CAP_HZ
    refuse = too_fast
    if refuse:
        raise TargetTooFastError(f"{target_hz} Hz is above the {CAP_HZ} Hz cap")


def hoisted_gate_state_shaped(achieved_hz: float, status: str) -> str:
    """Sink `gate_state` with the bar bound first — the branch tests a name, not a bar."""
    too_slow = achieved_hz < REQUIRED_HZ
    if too_slow:
        return GATE_STATE_FAIL
    return status


def hoisted_permit_shaped(passed: bool, swept_hz: tuple[float, ...]) -> dict[str, object]:
    """Sink `verdict_field` with the band test bound first — the field value is a name."""
    all_in_band = all(in_band(point_hz) for point_hz in swept_hz)
    return {"is_exit_permit": passed and all_in_band}


def meets_target_shaped(achieved_hz: float, target_hz: float) -> bool:
    """Sink `verdict_function`: a bool answering whether the rate was good enough."""
    return achieved_hz >= ON_TIME_RATIO * target_hz


def assert_rate_shaped(achieved_hz: float) -> None:
    """Sink `assert`: a frequency bar asserted rather than measured."""
    assert achieved_hz >= REQUIRED_HZ


def gate_state_shaped(achieved_hz: float) -> str:
    """Sink `gate_state` as a ternary: a frequency selects between two gate states."""
    return GATE_STATE_PASS if achieved_hz >= REQUIRED_HZ else GATE_STATE_FAIL


def gate_state_branch_shaped(achieved_hz: float) -> str:
    """Sink `gate_state` as an `if` statement — the same selection, spelled out."""
    if achieved_hz >= REQUIRED_HZ:
        return GATE_STATE_PASS
    return GATE_STATE_FAIL


def retry_state_shaped(achieved_hz: float, status: str) -> str:
    """Sink `gate_state` naming only the retry state, the one a `PASS`/`FAIL` pair omits.

    The state is spelled inline: a named constant would put a `Name` here, which the
    `GATE_STATE_` prefix rule matches instead of the bare-literal rule under test.
    """
    if achieved_hz < REQUIRED_HZ:
        return "RETRY_WITH_VARIANT"
    return status


def band_filtered_shaped(swept_hz: tuple[float, ...]) -> tuple[float, ...]:
    """Sink `filter`: a band predicate decides which measured points reach the verdict."""
    return tuple(point_hz for point_hz in swept_hz if in_band(point_hz))


def bar_filtered_shaped(swept_hz: tuple[float, ...]) -> tuple[float, ...]:
    """Sink `filter` with the bar written out — the same drop, no predicate to hide in."""
    return tuple(point_hz for point_hz in swept_hz if point_hz >= BAND_LOW_HZ)


def skip_out_of_band_shaped(swept_hz: tuple[float, ...]) -> tuple[float, ...]:
    """Sink `filter` as a loop that skips — the comprehension's statement form."""
    kept: list[float] = []
    for point_hz in swept_hz:
        if not in_band(point_hz):
            continue
        kept.append(point_hz)
    return tuple(kept)


def permit_field_shaped(passed: bool, swept_hz: tuple[float, ...]) -> dict[str, object]:
    """Sink `verdict_field`: a published permit conditioned on where the points sat."""
    return {"is_exit_permit": passed and all(in_band(point_hz) for point_hz in swept_hz)}


def permit_keyword_shaped(passed: bool, swept_hz: tuple[float, ...]) -> ProvisionalPermit:
    """Sink `verdict_field` as a constructor keyword — the same field, built not spelled."""
    return ProvisionalPermit(
        is_exit_permit=passed and all(in_band(point_hz) for point_hz in swept_hz)
    )


def reject_nonpositive_rate(requested_hz: float) -> None:
    """Not a verdict: a non-positive rate is malformed input, not a rate that failed."""
    if requested_hz <= 0.0:
        raise ValueError(f"publish rate must be positive, got {requested_hz}")


def resolve_rate_against_cap(requested_hz: float) -> str:
    """Not a verdict: an over-cap request is refused as a request, and nothing is judged."""
    if requested_hz > CAP_HZ:
        return f"publish rate {requested_hz} Hz exceeds the {CAP_HZ} Hz cap"
    return ""


def in_band(target_hz: float) -> bool:
    """Not a verdict: band bounds scope which samples are judged, they judge nothing."""
    return BAND_LOW_HZ <= target_hz <= BAND_HIGH_HZ


def band_label_shaped(point_hz: float) -> dict[str, object]:
    """Not a verdict: band membership published beside the point, the field naming no permit."""
    return {"target_hz": point_hz, "in_main_path": in_band(point_hz)}


def report_achieved_rate(median_cycle_sec: float, target_hz: float) -> dict[str, float]:
    """Not a verdict: what NORM-008 asks for instead — the rate stated, no bar applied."""
    return {"achieved_hz": 1.0 / median_cycle_sec, "target_hz": target_hz}
