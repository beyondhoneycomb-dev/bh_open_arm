"""The dataset preflight: `preflight(dataset, policy) -> PreflightReport`.

`02c` §1.2 WP-4A-02: this is the gate a dataset/policy pair passes before training
starts. It runs four fault classes over a dataset described by its `meta/info.json`
feature map and its `meta/stats.json` metric keys, and blocks on any of them:

1. an `observation.state` `names` order or shape defect (`observation.py`);
2. a structural-exclusion meta feature (`timestamp`/`index`/…) promoted into the
   policy-input namespace, judged with LeRobot's own `dataset_to_policy_features`
   classifier (`10` FR-TRN-076, D-7);
3. a quantile-normalized policy paired with statistics missing `q01`/`q99`
   (`10` FR-TRN-020, `08` FR-DAT-026); and
4. — folded into (1) — the torque-stripped-but-shape-kept configuration.

A `rename_map` on the policy spec is applied to feature KEYS for (2)/(3) and to
`observation.state` channel NAMES for (1); the two namespaces are disjoint, so one
map serves both. The classifier is imported from LeRobot and never reimplemented,
so the notion of "policy input feature" here is exactly the trainer's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lerobot.utils.constants import OBS_STR
from lerobot.utils.feature_utils import dataset_to_policy_features

from backend.training.preflight.observation import check_state_names, derive_observation_config
from backend.training.preflight.policy import (
    AUGMENT_SCRIPT,
    QUANTILE_MODES,
    REQUIRED_QUANTILE_KEYS,
    PolicyPreflightSpec,
)
from backend.training.preflight.report import (
    PreflightCode,
    PreflightFinding,
    PreflightReport,
)
from contracts.recorder import META_FEATURES

# The dtypes and key prefix that mark an image/depth feature. `dataset_to_policy_
# features` classifies by shape/prefix, and the synthetic fixture stores images as
# raw `uint8` (not `video`), so a prefix/dtype guard is what keeps a camera stream
# out of the numeric-statistics checks — an image never needs `q01`/`q99`.
_IMAGE_DTYPES = frozenset({"image", "video", "uint8"})
_IMAGE_KEY_PREFIX = f"{OBS_STR}.images."

# The default per-meta-feature body shape a real `meta/info.json` carries
# (LeRobot `DEFAULT_FEATURES` all have `shape (1,)`). The `CTR-REC@v1` contract
# sketch omits it, so it is supplied before classification — without a shape,
# `dataset_to_policy_features` raises on the very keys this check must examine.
_DEFAULT_META_SHAPE = (1,)


@dataclass(frozen=True)
class DatasetPreflightInput:
    """A dataset described exactly as far as preflight needs it.

    Attributes:
        info_features: The `features` map from `meta/info.json` — feature key to
            its `{dtype, shape, names, …}` body.
        stats: The `meta/stats.json` map — feature key to its metric map. Only the
            presence of metric keys (`q01`/`q99`) is read, never the values.
    """

    info_features: Mapping[str, Mapping[str, Any]]
    stats: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def _is_visual(key: str, body: Mapping[str, Any]) -> bool:
    """Whether a feature is an image/depth stream rather than a numeric vector.

    Args:
        key: The feature key.
        body: The feature body.

    Returns:
        (bool) True for a camera/depth feature, which never carries quantile stats.
    """
    if key.startswith(_IMAGE_KEY_PREFIX):
        return True
    if str(body.get("dtype")) in _IMAGE_DTYPES:
        return True
    return bool(body.get("is_depth_map"))


def _renamed_features(
    info_features: Mapping[str, Mapping[str, Any]], rename_map: Mapping[str, str]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Apply the key rename and complete meta shapes for the LeRobot classifier.

    Args:
        info_features: The declared feature map.
        rename_map: Old feature key to new feature key.

    Returns:
        (tuple) The renamed, shape-completed feature map ready for
            `dataset_to_policy_features`, and a new-key -> original-key origin map
            so a promoted feature can be traced back to the meta feature it was.
    """
    renamed: dict[str, dict[str, Any]] = {}
    origin: dict[str, str] = {}
    for key, body in info_features.items():
        new_key = rename_map.get(key, key)
        completed = dict(body)
        if "shape" not in completed:
            completed["shape"] = _DEFAULT_META_SHAPE
        renamed[new_key] = completed
        origin[new_key] = key
    return renamed, origin


def _check_structural_exclusion(
    dataset: DatasetPreflightInput, policy: PolicyPreflightSpec
) -> list[PreflightFinding]:
    """Block a structural-exclusion meta feature promoted to a policy input.

    LeRobot's `dataset_to_policy_features` drops `timestamp`/`index`/… through its
    `else -> continue`, so they can only become policy inputs by being renamed into
    the `observation`/`action` namespace or requested explicitly. Both are caught
    here (`10` FR-TRN-076, D-7).

    Args:
        dataset: The dataset under test.
        policy: The policy the dataset is paired with.

    Returns:
        (list[PreflightFinding]) One finding per promoted meta feature.
    """
    findings: list[PreflightFinding] = []
    renamed, origin = _renamed_features(dataset.info_features, policy.rename_map)
    policy_features = dataset_to_policy_features(renamed)

    for new_key in policy_features:
        source_key = origin.get(new_key, new_key)
        if source_key in META_FEATURES:
            findings.append(
                PreflightFinding(
                    code=PreflightCode.STRUCTURAL_FEATURE_PROMOTED,
                    channel_name=source_key,
                    component=None,
                    joint=None,
                    detail=(
                        f"structural-exclusion feature {source_key!r} is promoted to policy "
                        f"input {new_key!r}; dataset_to_policy_features excludes it by design "
                        "(else->continue), and a rename into the policy namespace defeats that "
                        "(10 FR-TRN-076, D-7)"
                    ),
                )
            )

    for requested in policy.input_features:
        if requested in META_FEATURES:
            findings.append(
                PreflightFinding(
                    code=PreflightCode.STRUCTURAL_FEATURE_PROMOTED,
                    channel_name=requested,
                    component=None,
                    joint=None,
                    detail=(
                        f"policy {policy.name!r} explicitly requests structural-exclusion "
                        f"feature {requested!r} as an input; it must stay excluded "
                        "(10 FR-TRN-076, D-7)"
                    ),
                )
            )

    return findings


def _check_quantile_stats(
    dataset: DatasetPreflightInput, policy: PolicyPreflightSpec
) -> list[PreflightFinding]:
    """Block a quantile-normalized policy when `q01`/`q99` are missing.

    The requirement is read from the policy's normalization modes, not its name: a
    numeric feature whose type maps to QUANTILES/QUANTILE10 must have `q01` and
    `q99` in `meta/stats.json`. Visual features are skipped — they carry no
    quantile stats and pi0.5 normalizes them by IDENTITY anyway. The remediation is
    suggested, never applied (`02c` §1.2 negative branch ③).

    Args:
        dataset: The dataset under test.
        policy: The policy the dataset is paired with.

    Returns:
        (list[PreflightFinding]) One finding per numeric feature missing quantiles.
    """
    if not policy.requires_quantiles():
        return []

    findings: list[PreflightFinding] = []
    renamed, origin = _renamed_features(dataset.info_features, policy.rename_map)
    policy_features = dataset_to_policy_features(renamed)

    for key, feature in policy_features.items():
        if _is_visual(key, renamed.get(key, {})):
            continue
        # A meta feature that only reached the policy namespace by a rename is a
        # structural-exclusion fault, reported there; demanding quantile stats for
        # a feature that must not be a policy input at all would be a cascade.
        if origin.get(key, key) in META_FEATURES:
            continue
        mode = policy.normalization_of(feature.type.value)
        if mode not in QUANTILE_MODES:
            continue
        present = dataset.stats.get(key, {})
        missing = [metric for metric in REQUIRED_QUANTILE_KEYS if metric not in present]
        if missing:
            findings.append(
                PreflightFinding(
                    code=PreflightCode.QUANTILE_STATS_MISSING,
                    channel_name=key,
                    component=None,
                    joint=None,
                    detail=(
                        f"policy {policy.name!r} normalizes {feature.type.value} feature "
                        f"{key!r} with {mode}, which needs {missing}; run {AUGMENT_SCRIPT} to "
                        "add quantile statistics. Not auto-run: it rewrites meta/stats.json and "
                        "so changes the stats hash (02c §0.4)"
                    ),
                )
            )

    return findings


def preflight(dataset: DatasetPreflightInput, policy: PolicyPreflightSpec) -> PreflightReport:
    """Run every preflight fault class over a dataset/policy pair.

    Args:
        dataset: The dataset described by its info/stats maps.
        policy: The policy the dataset will train.

    Returns:
        (PreflightReport) BLOCK with located findings when any fault is found, else
            PASS with an empty findings set (`02c` §1.2 ⑤).
    """
    config = derive_observation_config(dataset.info_features)
    effective_names = tuple(policy.rename_map.get(name, name) for name in config.names)

    findings: list[PreflightFinding] = []
    findings.extend(check_state_names(dataset.info_features, effective_names, config.bimanual))
    findings.extend(_check_structural_exclusion(dataset, policy))
    findings.extend(_check_quantile_stats(dataset, policy))

    return PreflightReport.from_findings(tuple(findings))
