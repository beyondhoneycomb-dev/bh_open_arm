"""Regenerate the provisional friction table from the synthetic demonstration (deterministic).

`python -m backend.friction.cli` runs the offline demonstration end to end — synthetic log,
per-joint fit, separation statistics, band, seed comparison — and writes the result to
`friction.provisional.yaml` under this package's tree. `--check` regenerates in memory and
reports whether the file on disk matches, the same drift guard `registry.generate --check`
applies to generated output.

The written file is provisional by construction: the writer has no path to a PG-FRIC-001 pass
(THE ONE RULE). The `.provisional.` filename, the `SYNTHETIC-NO-HARDWARE` provenance commit and
the `NOT_PASSED_DEFERRED_TO_HARDWARE` status all say so, so the artefact can demonstrate the
schema and the k-convention without ever reading as a validated v2 asset.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.dynamics.provenance import Provenance
from backend.friction.band import band_from_identification
from backend.friction.basis import InverseDynamicsBasis
from backend.friction.constants import FRICTION_YAML_FILENAME, IDENTIFIED_ROBOT_VERSION
from backend.friction.identify import identify_friction
from backend.friction.seed import V1_SEED_FRICTION, relative_error_table
from backend.friction.separation import separation_stats
from backend.friction.synthetic import generate_synthetic_log
from backend.friction.writer import build_friction_document, friction_yaml_text
from backend.gravity import Arm

DEFAULT_OUTPUT = Path(__file__).resolve().parent / FRICTION_YAML_FILENAME

# Fixed provenance so the generated artefact is byte-stable across runs. The commit field is a
# literal marker, not a real sha: this file was never captured on hardware, and the field must
# not read like a real identification.
_SYNTHETIC_PROVENANCE = Provenance(
    source_repo="bh_open_arm",
    commit_sha="SYNTHETIC-NO-HARDWARE",
    path=f"backend/friction/{FRICTION_YAML_FILENAME}",
    robot_version=IDENTIFIED_ROBOT_VERSION,
    identified_on="2026-07-22",
)


def render_provisional_text() -> str:
    """Run the deterministic synthetic demonstration and render its friction.yaml text.

    Returns:
        (str) The provisional friction document as YAML text.
    """
    basis = InverseDynamicsBasis(Arm.RIGHT)
    synthetic = generate_synthetic_log(basis)
    result = identify_friction(synthetic.log, basis, V1_SEED_FRICTION)
    stats = separation_stats(result)
    band = band_from_identification(synthetic.log, result)
    rel_errors = relative_error_table(result.params())
    document = build_friction_document(result, band, _SYNTHETIC_PROVENANCE, stats, rel_errors)
    return friction_yaml_text(document)


def main(argv: list[str] | None = None) -> int:
    """Write, or check, the provisional friction table.

    Args:
        argv: Command-line arguments; `sys.argv[1:]` when None.

    Returns:
        (int) Process exit status: non-zero when `--check` finds a mismatch.
    """
    parser = argparse.ArgumentParser(description="Regenerate the provisional friction table.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the file on disk against fresh output instead of writing it",
    )
    args = parser.parse_args(argv)
    text = render_provisional_text()
    if args.check:
        if not args.output.is_file():
            print(f"missing {args.output}", file=sys.stderr)
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != text:
            print(
                f"{args.output} is out of date; regenerate with `python -m backend.friction.cli`",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} is up to date")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
