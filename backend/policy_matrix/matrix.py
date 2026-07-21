"""The three-axis policy compatibility calculator (`10` FR-TRN-064/065).

The matrix is not two axes but three: {dataset observation config} x {policy
dimension ceiling} x {deploy-target capability}. A cell is blocked when ANY axis
blocks it, and every block carries the two fields `10` FR-TRN-064 requires — a
machine-readable code and a human sentence.

The three axes are computed from the three inputs this work package declares,
reusing their owners rather than restating their logic:

  * dimension axis — `backend.learning.policy_constraints` (WP-0C-07), fed the
    ceiling introspected off the installed config (`caps`), so the "48 > 32"
    block is the real constraint with the real ceiling, never a hardcoded 32;
  * dataset axis — `backend.learning.channel_groups` (WP-0C-07) turns an
    observation config into the exact `state_dim`/`action_dim` a synthetic
    recording would carry (24 / 48 / 16);
  * capability axis — the per-target guards in `targets.guards` named by
    `targets/matrix.yaml` (WP-ENV-02), evaluated against the deploy request, so
    FR-INF-033/034 are enforced by their existing owner.

Because the ceiling flows from introspection and the dataset dimension flows from
the observation config, a config that moves from 24 to 48 dims re-blocks the
32-capped policies with no edit to any table (acceptance ⑥): `usable_policies`
simply recomputes.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from backend.learning.channel_groups import action_channels, state_channels
from backend.learning.policy_constraints import (
    DatasetProfile,
    PolicyConstraintCode,
    PolicySpec,
    PolicyStructuralValidator,
)
from backend.policy_matrix.caps import introspect_caps
from backend.policy_matrix.registry import PolicyCompatEntry, load_registry
from targets.matrix import load_matrix

# The rate a synchronous inference loop is asked to run at when the request does
# not name one. It is the synthetic dataset / teleop control rate (`WP-0C-07`
# SyntheticDatasetSpec.fps), which is what FR-INF-034 compares against the measured
# onboard ceiling; above the ceiling, sync is blocked and async chunking is forced.
DEFAULT_CONTROL_FPS = 30

MODE_SYNC = "sync"
MODE_ASYNC = "async"

AXIS_DIMENSION = "dimension"
AXIS_CAPABILITY = "capability"


@dataclass(frozen=True)
class DatasetObsConfig:
    """A dataset's observation configuration — the first matrix axis.

    Attributes:
        bimanual: True for the two-arm layout, False for single-arm.
        use_velocity_and_torque: True keeps velocity and torque in the state
            vector (the 48-dim bimanual / 24-dim single-arm case), False collapses
            it to position-only.
    """

    bimanual: bool = True
    use_velocity_and_torque: bool = True

    def state_dim(self) -> int:
        """Return the flattened `observation.state` width for this config."""
        return len(
            state_channels(
                bimanual=self.bimanual, use_velocity_and_torque=self.use_velocity_and_torque
            )
        )

    def action_dim(self) -> int:
        """Return the position-only `action` width for this config."""
        return len(action_channels(bimanual=self.bimanual))


@dataclass(frozen=True)
class DeployRequest:
    """A deployment request — the third matrix axis.

    Attributes:
        target_id: A fleet target id, e.g. `jetson_orin`.
        mode: `sync` or `async`; the frequency ceiling only bites `sync`.
        fps: Requested inference rate for a sync loop.
        optimization_path: The optimisation path requested, e.g.
            `trt_full_pipeline`, or empty when none.
    """

    target_id: str
    mode: str = MODE_SYNC
    fps: float = DEFAULT_CONTROL_FPS
    optimization_path: str = ""

    def guard_context(self, policy: str) -> dict[str, Any]:
        """Build the context the `targets.guards` predicates read.

        Args:
            policy: The policy family, used as the guards' `policy_family`.

        Returns:
            (dict[str, Any]) The context `{target_id, policy_family, mode, fps,
                optimization_path}`.
        """
        return {
            "target_id": self.target_id,
            "policy_family": policy,
            "mode": self.mode,
            "fps": self.fps,
            "optimization_path": self.optimization_path,
        }


@dataclass(frozen=True)
class Block:
    """One reason a cell is blocked.

    Attributes:
        axis: Which axis blocked — `dimension` or `capability`.
        code: The machine-readable block code.
        human: The operator-facing sentence.
    """

    axis: str
    code: str
    human: str


@dataclass(frozen=True)
class MatrixCell:
    """The verdict for one {dataset, policy, deploy} triple.

    Attributes:
        policy: The policy family.
        dataset: The dataset observation config.
        deploy: The deploy request.
        blocks: Every block that applies; empty means allowed.
    """

    policy: str
    dataset: DatasetObsConfig
    deploy: DeployRequest
    blocks: tuple[Block, ...]

    @property
    def allowed(self) -> bool:
        """True when no axis blocks the cell."""
        return not self.blocks


@dataclass(frozen=True)
class PolicyMatrix:
    """The compatibility calculator over a loaded registry and target matrix.

    Attributes:
        entries: The policy compatibility registry, keyed by policy family.
        matrix_document: The parsed `targets/matrix.yaml`.
    """

    entries: dict[str, PolicyCompatEntry]
    matrix_document: dict[str, Any]

    def policies(self) -> tuple[str, ...]:
        """Return the registered policy families, in registry order."""
        return tuple(self.entries)

    def evaluate(self, dataset: DatasetObsConfig, policy: str, deploy: DeployRequest) -> MatrixCell:
        """Evaluate one {dataset, policy, deploy} triple across all three axes.

        Args:
            dataset: The dataset observation config.
            policy: A registered policy family.
            deploy: The deploy request.

        Returns:
            (MatrixCell) The verdict, carrying every block that applies.
        """
        blocks: list[Block] = []
        blocks.extend(self._dimension_blocks(dataset, policy))
        blocks.extend(self._capability_blocks(policy, deploy))
        return MatrixCell(policy=policy, dataset=dataset, deploy=deploy, blocks=tuple(blocks))

    def usable_policies(self, dataset: DatasetObsConfig, deploy: DeployRequest) -> tuple[str, ...]:
        """Return the policies whose cell is allowed for this dataset and deploy.

        This is the "usable policy matrix" of `10` FR-TRN-065: because the ceiling
        is introspected and the dimension is derived from `dataset`, flipping the
        observation config from 24 to 48 dims drops the 32-capped policies here
        with no manual edit to any table.

        Args:
            dataset: The dataset observation config.
            deploy: The deploy request.

        Returns:
            (tuple[str, ...]) Allowed policy families, in registry order.
        """
        return tuple(
            policy for policy in self.entries if self.evaluate(dataset, policy, deploy).allowed
        )

    def _dimension_blocks(self, dataset: DatasetObsConfig, policy: str) -> list[Block]:
        """Compute the dimension axis for one cell.

        The ceiling is introspected off the installed config and passed explicitly
        into `PolicySpec`, so the WP-0C-07 validator applies the real ceiling
        rather than its own hardcoded default.
        """
        entry = self.entries[policy]
        caps = introspect_caps(policy)
        spec = PolicySpec(
            policy_type=policy,
            max_state_dim=caps.max_state_dim,
            max_action_dim=caps.max_action_dim,
        )
        profile = DatasetProfile(
            state_dim=dataset.state_dim(),
            action_dim=dataset.action_dim(),
        )
        validator = PolicyStructuralValidator()
        blocks: list[Block] = []
        for violation in validator.validate(spec, profile):
            if violation.code is PolicyConstraintCode.DIMENSION_CAP_EXCEEDED:
                blocks.append(
                    Block(
                        axis=AXIS_DIMENSION, code=entry.block_reason.code, human=violation.message
                    )
                )
        return blocks

    def _capability_blocks(self, policy: str, deploy: DeployRequest) -> list[Block]:
        """Compute the deploy-target-capability axis for one cell.

        The guards evaluated are the ones `targets/matrix.yaml` names on the
        requested target (WP-ENV-02), so FR-INF-033/034 stay owned by the ENV band
        and this axis is a caller of them, not a second copy.
        """
        context = deploy.guard_context(policy)
        blocks: list[Block] = []
        for path in _target_blocked_paths(self.matrix_document, deploy.target_id):
            predicate = str(path.get("predicate", ""))
            guard = _resolve_guard(predicate)
            if guard is None:
                continue
            decision = guard(context)
            if decision.blocked:
                blocks.append(
                    Block(
                        axis=AXIS_CAPABILITY,
                        code=str(path.get("name", predicate)),
                        human=decision.reason,
                    )
                )
        return blocks


def build_matrix() -> PolicyMatrix:
    """Build a calculator from the on-disk registry and target matrix.

    Returns:
        (PolicyMatrix) A calculator over `contracts/policy_compat.yaml` and
            `targets/matrix.yaml`.
    """
    entries = {entry.policy: entry for entry in load_registry()}
    return PolicyMatrix(entries=entries, matrix_document=load_matrix())


def _target_blocked_paths(document: dict[str, Any], target_id: str) -> list[dict[str, Any]]:
    """Return the blocked-path entries `targets/matrix.yaml` names on a target."""
    for target in document.get("targets") or []:
        if str(target.get("target_id", "")) == target_id:
            return list(target.get("blocked_paths") or [])
    return []


def _resolve_guard(dotted: str) -> Any:
    """Resolve a dotted guard name to its callable, or None when it does not exist."""
    module_name, _, attr = dotted.rpartition(".")
    if not module_name:
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return None
    guard = getattr(module, attr, None)
    return guard if callable(guard) else None
