"""Write the identified friction to a `friction.yaml`, carrying every acceptance in its metadata.

The upstream `friction.yaml` is a zero-byte file: v2 friction is unidentified (spec 09
FR-SIM-049). This writer fills it. One document carries all four WP-2B-07 acceptances:

* ① the per-joint parameters plus each joint's fit quality and separation verdict;
* ② the `k_eff = 0.1 * k` convention, stated in a dedicated metadata block so no consumer can
  miss that the stored `k` is a tenth of the tanh slope it names;
* ③ the identification band, recorded as a function of the logging frequency;
* ④ the per-joint relative error against the v1 seed.

The writer cannot emit a PG-FRIC-001 pass. There is no parameter that sets the gate status to
passed: a synthetic-log fit is always written `NOT_PASSED_DEFERRED_TO_HARDWARE` with a
`SYNTHETIC_EXCITATION_LOG` basis and a re-verification hook. A real pass is produced only by
re-running the identical fit against real captures through `reverify`, never here (THE ONE
RULE). The canonical upstream `friction.yaml` lives in the external `openarm_description` tree,
not in this repository, so this writer's output lives under this package's own tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.dynamics.provenance import Provenance
from backend.friction.band import IdentificationBand, band_from_identification
from backend.friction.constants import (
    BASIS_SYNTHETIC_LOG,
    FIXTURE_ENV_VAR,
    K_EFF_SCALE,
    PARAM_KEY_FC,
    PARAM_KEY_FO,
    PARAM_KEY_FV,
    PARAM_KEY_K,
    PG_FRIC_001_STATUS_DEFERRED,
)
from backend.friction.identify import IdentificationResult
from backend.friction.log import ExcitationLog
from backend.friction.seed import RelativeError, relative_error_table
from backend.friction.separation import SeparationStat, separation_stats

_MODEL_EXPRESSION = "tau_fric(omega) = Fo + Fv*omega + Fc*tanh(k_eff*omega)"
_ROUND_DIGITS = 6

_K_CONVENTION_NOTE = (
    "The runtime applies k_eff = 0.1 * k (control.cpp ComputeFriction coef_tmp=0.1, spec 04 "
    "FR-MAN-034); the stored k equals fitted k_eff / 0.1. Writing the raw slope as k would "
    "deploy a friction ten times too soft in the stiction knee."
)
_BAND_NOTE = (
    "omega_lo is a function of the logging frequency: a lower rate raises it and eats into the "
    "stiction knee first (spec 12 §2.1). knee_resolved is false when the tightest tanh knee "
    "falls below omega_lo, i.e. the low-rate log did not cover it."
)
_STATUS_REASON = (
    "Identified from a synthetic excitation log to prove convergence and residual separation. "
    "This is NOT a PG-FRIC-001 pass: real friction values need real excitation logs (WP-2B-06 "
    "on hardware) and a PG-J7-001 torque-scale pass, without which the identified Fc/Fv/Fo are "
    "unverified and the J7 scale may be off by 2x."
)
_REAL_PASS_REQUIRES = (
    "PG-J7-001 PASS (RID 23 read: DM4310 vs DM3507 torque scale)",
    "WP-2B-06 real excitation logs captured no-transmit (WP-2B-05)",
    "J2 zero +pi/2 shift applied (WP-2B-01)",
)


def _round(value: float) -> float:
    """Round a float to the writer's fixed precision, for readable and drift-stable output."""
    return round(float(value), _ROUND_DIGITS)


def _joint_block(
    result: IdentificationResult, stats: tuple[SeparationStat, ...]
) -> list[dict[str, Any]]:
    """Build the per-joint parameter and fit-quality rows (acceptance ①).

    Args:
        result: The identification result.
        stats: The per-joint separation statistics, aligned with `result.fits`.

    Returns:
        (list[dict[str, Any]]) One mapping per joint, joint1..joint7 order.
    """
    rows: list[dict[str, Any]] = []
    for fit, stat in zip(result.fits, stats, strict=True):
        params = fit.params
        rows.append(
            {
                "index": fit.joint_index + 1,
                PARAM_KEY_FO: _round(params.f_o),
                PARAM_KEY_FV: _round(params.f_v),
                PARAM_KEY_FC: _round(params.f_c),
                PARAM_KEY_K: _round(params.k),
                "k_eff": _round(params.k_eff),
                "fit_residual_rms_nm": _round(fit.residual_rms_nm),
                "converged": fit.converged,
                "separated": stat.separated,
                "corr_gravity": _round(stat.corr_gravity),
                "corr_coriolis": _round(stat.corr_coriolis),
                "corr_inertia": _round(stat.corr_inertia),
                "r2": _round(stat.r2),
            }
        )
    return rows


def _band_block(band: IdentificationBand) -> dict[str, Any]:
    """Build the identification-band metadata (acceptance ③)."""
    return {
        "log_freq_hz": _round(band.log_freq_hz),
        "omega_lo_rad_s": _round(band.omega_lo_rad_s),
        "omega_hi_rad_s": _round(band.omega_hi_rad_s),
        "knee_omega_rad_s": _round(band.knee_omega_rad_s),
        "knee_resolved": band.knee_resolved,
        "note": _BAND_NOTE,
    }


def _seed_block(rows: tuple[RelativeError, ...]) -> dict[str, Any]:
    """Build the per-joint relative-error-against-seed metadata (acceptance ④)."""
    return {
        "seed": "v1 follower.yaml (robot_version 1.0, not vendored)",
        "joints": [
            {
                "index": row.joint_index + 1,
                "rel_Fo": _round(row.rel_f_o),
                "rel_Fv": _round(row.rel_f_v),
                "rel_Fc": _round(row.rel_f_c),
                "rel_k_eff": _round(row.rel_k_eff),
                "rel_l2": _round(row.rel_l2),
            }
            for row in rows
        ],
    }


def build_friction_document(
    result: IdentificationResult,
    band: IdentificationBand,
    provenance: Provenance,
    stats: tuple[SeparationStat, ...],
    rel_errors: tuple[RelativeError, ...],
) -> dict[str, Any]:
    """Assemble the full friction.yaml document from an identification and its statistics.

    Args:
        result: The identification result (the per-joint fits).
        band: The identification band.
        provenance: The asset provenance stamp (robot_version 2.0 for an identified v2 asset).
        stats: The per-joint separation statistics.
        rel_errors: The per-joint relative error against the seed.

    Returns:
        (dict[str, Any]) The document, ready to serialise. Its status is always provisional.
    """
    return {
        "schema": "openarm.friction/v1",
        "model": _MODEL_EXPRESSION,
        "k_convention": {
            "applied": "k_eff = 0.1 * k",
            "scale": K_EFF_SCALE,
            "note": _K_CONVENTION_NOTE,
        },
        "status": {
            "pg_fric_001": PG_FRIC_001_STATUS_DEFERRED,
            "provisional": True,
            "basis": BASIS_SYNTHETIC_LOG,
            "reason": _STATUS_REASON,
            "real_pass_requires": list(_REAL_PASS_REQUIRES),
            "reverify_hook": {
                "module": "backend.friction.reverify",
                "env_var": FIXTURE_ENV_VAR,
            },
        },
        "provenance": provenance.to_dict(),
        "identification_band": _band_block(band),
        "joints": _joint_block(result, stats),
        "seed_comparison": _seed_block(rel_errors),
    }


def friction_yaml_text(document: dict[str, Any]) -> str:
    """Render a friction document to its YAML text, preserving key order.

    Args:
        document: The document from `build_friction_document`.

    Returns:
        (str) The serialised YAML, deterministic for a given document.
    """
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, default_flow_style=False)


def write_friction_yaml(path: Path, document: dict[str, Any]) -> None:
    """Serialise a friction document to a YAML file, preserving key order.

    Args:
        path: The destination path (under this package's tree, not a protected asset tree).
        document: The document from `build_friction_document`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(friction_yaml_text(document), encoding="utf-8")


def write_identified_friction(
    path: Path, result: IdentificationResult, log: ExcitationLog, provenance: Provenance
) -> dict[str, Any]:
    """Compute the statistics, band and seed comparison, then write the friction document.

    Args:
        path: The destination path.
        result: The identification result.
        log: The excitation log the result came from (for the band's logging rate and edges).
        provenance: The asset provenance stamp.

    Returns:
        (dict[str, Any]) The document written.
    """
    stats = separation_stats(result)
    band = band_from_identification(log, result)
    rel_errors = relative_error_table(result.params())
    document = build_friction_document(result, band, provenance, stats, rel_errors)
    write_friction_yaml(path, document)
    return document
