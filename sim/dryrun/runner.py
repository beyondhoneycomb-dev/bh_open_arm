"""The dry-run runner: validate a trajectory against all six checks (`09` §3.5).

Ties WP-0C-09 together for mode (c). A runner refuses to exist until three things
hold, in the order the plan requires:

- The asset passes the WP-0C-03 invariant (``verify_fixed_asset``), so torque check
  ③ is not running on an asset whose J7 tMax is twice wrong (acceptance ⑮).
- The hard gate is the canonical MuJoCo backend (``designate_hard_gate``), never
  Isaac (acceptance ⑫, `09` FR-SIM-135).
- A clamp canon is selected for position and velocity, or the run is refused
  (``ClampCanon``; `09` FR-SIM-031/032/132).

``run_trajectory`` walks the waypoints, and at each one runs all six checks over the
forward-evaluated state, computing torque from *inverse dynamics* (the non-inert
FR-SIM-133 source), and aggregates every violation — distinctly coded, each stamped
with its sim time — into one ``DryRunVerdict``. The verdict feeds the interlock; a
non-passing verdict hard-blocks real transmission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import mujoco

import sim.mjcf
from contracts.action.channels import AcceptedPositionAction
from contracts.units.conversions import deg_to_rad
from packages.lerobot_robot_openarm_mujoco.backend_selector import Backend
from sim.dryrun.asset_ref import verify_fixed_asset
from sim.dryrun.backend_gate import HardGate, designate_hard_gate
from sim.dryrun.canon import ClampCanon
from sim.dryrun.checks.cell_collision import check_cell_collision
from sim.dryrun.checks.lifter_stroke import check_lifter_stroke
from sim.dryrun.checks.position import check_position_limits
from sim.dryrun.checks.self_collision import check_self_collision
from sim.dryrun.checks.torque import check_torque_limits, measured_efforts_via_inverse
from sim.dryrun.checks.velocity import check_velocity_limits
from sim.dryrun.limits import torque_limits_nm
from sim.dryrun.topology import arm_joint_addresses, lifter_address
from sim.dryrun.violation import DryRunVerdict, Violation
from sim.mujoco.sim_sync import POSITION_SUFFIX, action_channel_order

# The cell scene the dry-run resolves over: the lifter + cell collision geoms plus
# the attached J7-corrected bimanual model (`09` §1.1, WP-0C-03).
_CELL_ASSET = Path(sim.mjcf.__file__).resolve().parent / "v2" / "cell.xml"

# The channel-name suffix (`.pos`) stripped to recover a motor key from a CTR-ACT
# position channel name.
_POSITION_CHANNEL_SUFFIX = f".{POSITION_SUFFIX}"


@dataclass(frozen=True)
class Waypoint:
    """One trajectory sample to validate.

    A trajectory the dry-run gates is, in the running system, a sequence of CTR-ACT
    position actions (`WP-0A-02`) that the IK adapter (`WP-0C-02`) produced from VR;
    ``from_accepted_action`` and ``from_ik_outcome`` are the sanctioned bridges that
    turn those upstream artifacts into a waypoint, so the dry-run validates exactly
    what would be transmitted rather than a re-typed copy.

    Attributes:
        sim_t: Simulation time in seconds, stamped onto any violation here.
        positions_rad: Motor key (and optionally the lifter) to joint position in
            radians; joints omitted stay at the model zero.
        velocities_rad_s: Motor key to joint velocity in radians/second; omitted
            joints are treated as zero (a quasi-static holding-torque sample).
    """

    sim_t: float
    positions_rad: Mapping[str, float]
    velocities_rad_s: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def from_accepted_action(cls, action: AcceptedPositionAction, sim_t: float = 0.0) -> Waypoint:
        """Build a waypoint from a CTR-ACT position action (`WP-0A-02`).

        The action is the degree payload the real robot would receive; this crosses
        each channel to radians through the sanctioned CTR-UNIT conversion and keys
        it by motor, so the dry-run validates the exact transmission payload. Gripper
        channels are carried through but not judged by the arm checks.

        Args:
            action: The accepted position action, one ``Deg`` per action channel.
            sim_t: Simulation time to stamp on any violation.

        Returns:
            (Waypoint) The trajectory sample in radians.
        """
        channels = action_channel_order(bimanual=True)
        positions_rad = {
            name[: -len(_POSITION_CHANNEL_SUFFIX)]: deg_to_rad(value).value
            for name, value in zip(channels, action.values, strict=True)
        }
        return cls(sim_t=sim_t, positions_rad=positions_rad)

    @classmethod
    def from_ik_outcome(cls, outcome: object, sim_t: float = 0.0) -> Waypoint:
        """Build a waypoint from the IK adapter's output (`WP-0C-02`).

        The IK adapter (``sim.ik.adapter``) is the upstream that produces the
        trajectory the dry-run validates; this consumes its ``IkOutcome`` directly,
        so a caller feeds the dry-run the real IK result rather than transcribing it.

        Args:
            outcome: An ``IkOutcome`` from ``sim.ik.adapter``.
            sim_t: Simulation time to stamp on any violation.

        Returns:
            (Waypoint) The trajectory sample in radians.

        Raises:
            TypeError: If ``outcome`` is not an ``IkOutcome``.
            ValueError: If the outcome held with no accepted action to validate.
        """
        from sim.ik.adapter import IkOutcome

        if not isinstance(outcome, IkOutcome):
            raise TypeError(f"expected an IkOutcome, got {type(outcome).__name__}")
        if outcome.accepted is None:
            raise ValueError("IK outcome held with no accepted action; nothing to dry-run")
        return cls.from_accepted_action(outcome.accepted, sim_t=sim_t)


class DryRunRunner:
    """Validate trajectories against the six checks on the MuJoCo hard gate.

    Ownership/lifecycle: owns one compiled model/data for the cell scene. Not
    thread-safe. Construction verifies the asset, gate, and canon up front, so a
    constructed runner is proof the run is permitted; ``run_trajectory`` may then be
    called repeatedly.
    """

    def __init__(self, canon: ClampCanon, asset_path: Path | None = None) -> None:
        """Build a runner after verifying asset, gate, and canon.

        Args:
            canon: The selected position/velocity clamp canon (refuses if unselected).
            asset_path: The cell scene to load; defaults to the WP-0C-03 cell asset.

        Raises:
            UnfixedAssetError: If the bimanual asset fails the WP-0C-03 invariant.
            IsaacHardGateError: If the hard gate does not resolve to MuJoCo.
            ClampCanonUnselectedError: If the canon is unselected (raised building it).
        """
        self._asset_digest = verify_fixed_asset()
        self._gate: HardGate = designate_hard_gate(Backend.MUJOCO)
        self._canon = canon
        self._model = mujoco.MjModel.from_xml_path(str(asset_path or _CELL_ASSET))
        self._data = mujoco.MjData(self._model)
        self._torque_limits = torque_limits_nm()

    @property
    def asset_digest(self) -> str:
        """The verified fixed-asset digest this runner is bound to (acceptance ⑮)."""
        return self._asset_digest

    def run_trajectory(self, waypoints: Sequence[Waypoint]) -> DryRunVerdict:
        """Validate every waypoint against all six checks, aggregating violations.

        Args:
            waypoints: The trajectory samples to validate.

        Returns:
            (DryRunVerdict) All violations found, plus the asset digest and backend.
        """
        violations: list[Violation] = []
        for waypoint in waypoints:
            violations.extend(self._check_waypoint(waypoint))
        return DryRunVerdict(
            violations=tuple(violations),
            asset_digest=self._asset_digest,
            backend=self._gate.backend.value,
        )

    def _check_waypoint(self, waypoint: Waypoint) -> list[Violation]:
        """Run all six checks over one waypoint's forward-evaluated state."""
        model, data = self._model, self._data
        self._apply_state(waypoint)
        mujoco.mj_forward(model, data)

        bounds = self._canon.resolve_position_bounds(model)
        velocity_limits = self._canon.resolve_velocity_limits()
        found: list[Violation] = []
        found.extend(check_position_limits(model, data, bounds, waypoint.sim_t))
        found.extend(check_velocity_limits(model, data, velocity_limits, waypoint.sim_t))
        found.extend(check_lifter_stroke(model, data, waypoint.sim_t))
        found.extend(check_cell_collision(model, data, waypoint.sim_t))
        found.extend(check_self_collision(model, data, waypoint.sim_t))

        # Torque from inverse dynamics at zero acceleration: the quasi-static holding
        # torque, the non-inert FR-SIM-133 source, not the clamped actuator force.
        data.qacc[:] = 0.0
        efforts = measured_efforts_via_inverse(model, data)
        found.extend(check_torque_limits(efforts, self._torque_limits, waypoint.sim_t))
        return found

    def _apply_state(self, waypoint: Waypoint) -> None:
        """Reset to zero, then write the waypoint's positions and velocities."""
        mujoco.mj_resetData(self._model, self._data)
        addresses = {a.motor_key: a for a in arm_joint_addresses(self._model)}
        addresses[lifter_address(self._model).motor_key] = lifter_address(self._model)
        for motor_key, value in waypoint.positions_rad.items():
            address = addresses.get(motor_key)
            if address is not None:
                self._data.qpos[address.qpos_adr] = value
        for motor_key, value in waypoint.velocities_rad_s.items():
            address = addresses.get(motor_key)
            if address is not None:
                self._data.qvel[address.dof_adr] = value
