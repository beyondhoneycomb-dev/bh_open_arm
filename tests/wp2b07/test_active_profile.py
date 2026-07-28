"""NORM-012 — the running friction profile answers "which robot is this, and was it re-identified".

The ruling adopted the v1 seed as the shipping default because it is the only measured friction
that exists. Its stated cost is a standing bias in the observer residual, which shifts the
collision thresholds calibrated against it. That cost is only manageable if the operator can ask
what is running, so this pins the query rather than the numbers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.friction.active import ActiveFrictionProfile, load_profile, v1_seed_profile
from backend.friction.constants import ARM_JOINT_COUNT, FRICTION_YAML_FILENAME
from backend.friction.errors import FrictionIdentificationError

_FRICTION_PACKAGE = Path(__file__).resolve().parents[2] / "backend" / "friction"
_WRITTEN_TABLE = _FRICTION_PACKAGE / FRICTION_YAML_FILENAME


def test_the_shipping_default_reports_itself_as_the_v1_seed() -> None:
    """The default profile must not read as re-identified — that is the whole point of asking."""
    profile = v1_seed_profile()

    assert profile.provenance.robot_version == "1.0"
    assert profile.is_reidentified is False
    assert len(profile.params) == ARM_JOINT_COUNT


def test_the_record_carries_both_the_version_and_the_verdict() -> None:
    """An operator query gets the stamp and the derived answer, not one without the other."""
    record = v1_seed_profile().as_record()

    assert record["robot_version"] == "1.0"
    assert record["is_reidentified"] is False
    assert record["provenance"]["source_repo"] == "enactic/openarm_teleop"


def test_a_written_table_reads_back_with_the_stamp_it_carries() -> None:
    """The committed table is stamped v2, so a profile loaded from it reports re-identified."""
    profile = load_profile(_WRITTEN_TABLE)

    assert len(profile.params) == ARM_JOINT_COUNT
    assert profile.provenance.robot_version == "2.0"
    assert profile.is_reidentified is True


def test_a_table_with_no_stamp_is_refused_rather_than_assumed_identified(tmp_path: Path) -> None:
    """Refusing is the safe direction: a defaulted "identified" hides the bias being looked for."""
    document = yaml.safe_load(_WRITTEN_TABLE.read_text(encoding="utf-8"))
    del document["provenance"]
    stripped = tmp_path / FRICTION_YAML_FILENAME
    stripped.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(FrictionIdentificationError, match="provenance"):
        load_profile(stripped)


def test_the_running_observer_can_be_asked_what_friction_it_subtracts() -> None:
    """The query has to reach the live observer, not just a module nobody calls.

    NORM-012 says the *running* profile is queryable. `observer.model.friction_profile` is that
    path; if it broke, the seed bias would be undiagnosable from a residual trace.
    """
    from backend.gmo.model import GmoModelTerms
    from backend.gmo.observer import MomentumObserver

    observer = MomentumObserver(GmoModelTerms(), gain=90.0)
    profile = observer.model.friction_profile

    assert profile.provenance.robot_version == "1.0"
    assert profile.is_reidentified is False


def test_a_wrong_width_parameter_set_is_refused() -> None:
    """A short set would silently mis-index joints against the seven-joint residual."""
    seed = v1_seed_profile()

    with pytest.raises(FrictionIdentificationError, match=str(ARM_JOINT_COUNT)):
        ActiveFrictionProfile(params=seed.params[:-1], provenance=seed.provenance)
