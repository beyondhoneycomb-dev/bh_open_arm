"""The `11` §2.6 expected-inference-frequency lookup — sourced, never estimated.

`FR-INF-034` requires the matrix to present the expected inference frequency of a
hardware/policy pair "from the `11` §2.6 table", and `FR-TRN-004` forbids showing an
estimated number as if it were measured. So this module is a *lookup*, not a formula:
`expected_hz` returns a value only when a `11` §2.6 row supplies it, and otherwise
returns `None` with a source line naming why the number is unknown — it never computes,
interpolates, or borrows a nearby platform's figure. `estimated` is False by
construction; there is no code path that sets it True.

`11` §2.6's one primary quantitative source is the Isaac-GR00T deployment benchmark
(GR00T N1.7, 4 denoising steps, 1 camera). It measures GR00T only, and among the four
fleet targets it covers only Jetson Orin. Therefore:

  * (jetson_orin, groot) has a sourced ceiling — 4.6 Hz, the best achievable mode
    (TensorRT DiT-only; the full-pipeline row does not exist for Orin because TRT 10.3
    cannot compile the backbone engine, FR-INF-033);
  * every other (target, policy) pair has NO `11` §2.6 row. That is a missing
    measurement to be resolved by a self-bench (`NFR-INF-005`), never an estimate. The
    honest value is `None`.

This is deliberately NOT `targets.guards.INFERENCE_CEILING_HZ`. That runtime helper
carries a `(jetson_nano, groot)` entry, but `11` §2.6 has no Jetson Nano row, so
presenting a Nano ceiling as a §2.6 lookup would be the estimate FR-TRN-004 forbids.
The source-of-record lookup lives here and reproduces only what §2.6 actually states;
`estimate_violations` is the machine proof that it does (CG-4B-04f).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.compat.deploy_matrix.target import DeploymentTarget

# The policy family the `11` §2.6 benchmark measures. It is also, in the bimanual 48-dim
# configuration, the only inference candidate that clears the dimension cap for an edge
# target (SmolVLA/pi0/pi05 are 32-capped, `02c` §6.1 footnote), so the table happens to
# cover the one policy Orin onboard inference can run.
POLICY_GROOT = "groot"

# The provenance FR-TRN-004 demands on every sourced value. The per-row source appends
# the platform and mode so the reader can find the exact line the number came from.
SOURCE_2_6 = (
    "11 §2.6 (NVIDIA/Isaac-GR00T/scripts/deployment/README.md; GR00T N1.7, "
    "4 denoising steps, 1 camera)"
)


@dataclass(frozen=True)
class Groot26Row:
    """One row of the `11` §2.6 GR00T deployment benchmark, transcribed faithfully.

    The step latencies are carried alongside the end-to-end figure so a reader can see
    why Orin's ceiling is what it is (the 128 ms backbone stays in PyTorch), not just
    the headline Hz. Every field is a value the source table states; none is derived.

    Attributes:
        platform: The benchmarked platform label, as `11` §2.6 names it.
        mode: The inference mode (e.g. `TensorRT (DiT-only)`).
        data_proc_ms: Data-processing latency, milliseconds.
        backbone_ms: Backbone latency, milliseconds.
        action_head_ms: Action-head latency, milliseconds.
        e2e_ms: End-to-end latency, milliseconds.
        hz: The measured inference frequency, Hz.
    """

    platform: str
    mode: str
    data_proc_ms: float
    backbone_ms: float
    action_head_ms: float
    e2e_ms: float
    hz: float


# The `11` §2.6 table, verbatim. This is the "11 §2.6 lookup data" WP-4B-04 consumes; it
# is not re-derived anywhere. Rows for platforms outside the fleet (H100, RTX Pro 6000
# Blackwell, L40, DGX Spark, AGX Thor) are kept so the table is the whole source, and so
# `_best_row` selects the achievable ceiling for a platform rather than a hardcoded pick.
GROOT_2_6_TABLE: tuple[Groot26Row, ...] = (
    Groot26Row("H100 80GB", "PyTorch Eager", 6.2, 31.3, 48.2, 85.8, 11.7),
    Groot26Row("H100 80GB", "TensorRT (Full)", 6.2, 8.8, 12.3, 27.9, 35.9),
    Groot26Row("RTX Pro 6000 Blackwell", "TensorRT (Full)", 4.8, 9.9, 13.2, 27.9, 35.9),
    Groot26Row("L40", "TensorRT (Full)", 6.6, 13.1, 18.8, 38.4, 26.0),
    Groot26Row("DGX Spark", "TensorRT (Full)", 13.14, 33.43, 52.37, 98.6, 10.1),
    Groot26Row("AGX Thor", "TensorRT (Full)", 8.21, 28.89, 56.64, 93.8, 10.7),
    Groot26Row("Jetson Orin", "PyTorch Eager", 9.45, 127.6, 205.39, 342.8, 2.9),
    Groot26Row("Jetson Orin", "TensorRT (DiT-only)", 9.45, 128.38, 78.6, 216.5, 4.6),
)

# Fleet target -> its `11` §2.6 platform label. Only Jetson Orin appears in the table;
# the other three fleet targets have no §2.6 row and resolve to None (unknown, deferred
# to self-bench), never to a lookalike platform's number. RTX 5090 is Blackwell but is
# NOT "RTX Pro 6000 Blackwell"; RTX A6000 is Ampere but is NOT "L40" — mapping either
# would be the estimate FR-TRN-004 forbids.
_TARGET_TO_PLATFORM: dict[DeploymentTarget, str] = {
    DeploymentTarget.JETSON_ORIN: "Jetson Orin",
}


@dataclass(frozen=True)
class ExpectedHz:
    """An expected inference frequency with its provenance (`FR-INF-034`/`FR-TRN-004`).

    Attributes:
        hz: The looked-up ceiling in Hz, or None when `11` §2.6 has no row for the pair
            (unknown, to be resolved by self-bench — never estimated).
        source: The provenance line. For a sourced value it names the §2.6 row; for an
            unknown value it names why the number is unknown and what resolves it.
        mode: The inference mode the sourced ceiling assumes, or None when unknown.
        estimated: Always False. Present so a consumer can assert the invariant
            (CG-4B-04f) rather than trust the docstring; no code path sets it True.
    """

    hz: float | None
    source: str
    mode: str | None
    estimated: bool


def _best_row(platform: str) -> Groot26Row:
    """Return a platform's achievable ceiling — its highest-Hz `11` §2.6 row.

    The ceiling is the best supported mode's figure: for Jetson Orin that is TensorRT
    DiT-only (4.6 Hz), since the full-pipeline mode has no Orin row (FR-INF-033). This
    reads the maximum from the table rather than hardcoding which mode wins, so the
    selection moves with the source if a faster mode is ever added.

    Args:
        platform: A platform label present in `GROOT_2_6_TABLE`.

    Returns:
        (Groot26Row) The highest-Hz row for the platform.

    Raises:
        KeyError: When no row exists for the platform — a caller must map only platforms
            the table covers.
    """
    rows = [row for row in GROOT_2_6_TABLE if row.platform == platform]
    if not rows:
        raise KeyError(f"no 11 §2.6 row for platform {platform!r}")
    return max(rows, key=lambda row: row.hz)


def expected_hz(target: DeploymentTarget, policy: str) -> ExpectedHz:
    """Look up a (target, policy) pair's expected inference frequency (`FR-INF-034`).

    Returns a sourced value only when `11` §2.6 supplies one; otherwise returns an
    unknown (`hz=None`) with a source line naming why and what resolves it. Never
    estimates, interpolates, or borrows another platform's number (`FR-TRN-004`).

    Args:
        target: The deployment target.
        policy: The policy family, e.g. `groot`.

    Returns:
        (ExpectedHz) The sourced ceiling, or an unknown carrying its provenance.
    """
    if policy != POLICY_GROOT:
        return ExpectedHz(
            hz=None,
            source=(
                f"no 11 §2.6 row for policy {policy!r} (§2.6 measures GR00T only; LeRobot "
                "ACT/SmolVLA step latency has no primary source) — self-bench required "
                "(NFR-INF-005)"
            ),
            mode=None,
            estimated=False,
        )
    platform = _TARGET_TO_PLATFORM.get(target)
    if platform is None:
        return ExpectedHz(
            hz=None,
            source=(
                f"no 11 §2.6 row for target {target.value!r} (§2.6 covers Jetson Orin "
                "among the fleet) — self-bench required (NFR-INF-005)"
            ),
            mode=None,
            estimated=False,
        )
    row = _best_row(platform)
    return ExpectedHz(
        hz=row.hz,
        source=f"{SOURCE_2_6} — {row.platform}, {row.mode}",
        mode=row.mode,
        estimated=False,
    )


def sourced_hz_values() -> frozenset[float]:
    """Return every Hz value the `11` §2.6 table states — the sourced-value universe."""
    return frozenset(row.hz for row in GROOT_2_6_TABLE)


def estimate_violations(
    pairs: tuple[tuple[DeploymentTarget, str], ...],
) -> tuple[str, ...]:
    """Prove no presented `expected_hz` is an estimate (CG-4B-04f).

    An expected frequency is legitimate only if it is either unknown (`None`) or a value
    the `11` §2.6 table actually states. This walks the given pairs and reports any that
    are flagged estimated, or that carry a non-None Hz absent from the source table — a
    number we would have had to invent.

    Args:
        pairs: The (target, policy) pairs to audit.

    Returns:
        (tuple[str, ...]) One problem line per estimated value; empty when all are
            sourced or honestly unknown.
    """
    sourced = sourced_hz_values()
    problems: list[str] = []
    for target, policy in pairs:
        result = expected_hz(target, policy)
        if result.estimated:
            problems.append(f"{target.value}/{policy}: expected_hz marked estimated")
        if result.hz is not None and result.hz not in sourced:
            problems.append(
                f"{target.value}/{policy}: expected_hz {result.hz} is not a 11 §2.6 value"
            )
    return tuple(problems)
