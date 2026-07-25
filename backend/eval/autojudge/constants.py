"""Fixed values of the WP-4C-07 auto-judge protocol (`02c` §3.7).

Every literal here is a decision the spec fixed, not a knob this package invented.
`FR-INF-079` fixes the two load-bearing tokens — the canon label source is HUMAN,
and a disagreement rate over threshold disables the auto-judge and reverts to human
labels. `FR-SIM-095` fixes the sidecar tag that separates a model-judged episode
from a human-labelled one. The Q11 order (`11` §5-Q11) fixes the sequence a package
must satisfy before auto-judge may ever be enabled.

The disagreement threshold is the one value the spec does not pin to a number:
`FR-INF-079` names the mechanism ("over a threshold -> disable") but leaves the
figure to be set against measured precision/recall, which is DEFERRED (the real VLM
run and the human reference labels are not landed). So the default here is an
explicit placeholder, named as one, not a measured operating point — exactly the
`02c` §1.5 "미사용을 명시적 값으로" discipline the sibling packages use.
"""

from __future__ import annotations

# `FR-INF-079` / `FR-SIM-095`: the success-rate canon is the human label, and a
# model-judged episode is tagged distinctly from a human-labelled one. These are the
# exact tokens the sidecar stamps and the static checks (CG-4C-07a/c) read.
LABEL_SOURCE_HUMAN = "HUMAN"
LABEL_SOURCE_MODEL = "MODEL"
SIDECAR_TAG_MODEL_JUDGED = "model-judged"
SIDECAR_TAG_HUMAN_LABELED = "human-labeled"

# `FR-INF-079`: a placeholder disagreement threshold, NOT a measured operating point.
# The real figure is set against the VLM's precision/recall on human reference
# labels, and that measurement is DEFERRED (WP-4C-02 labels + the real Cosmos
# Reason 2 run are Human/HW bands). A rate STRICTLY above this disables the
# auto-judge (`trigger.evaluate_disable`); the comparison is strict so a rate
# exactly at the threshold does not yet trip — the spec says "exceeds", not "reaches".
DEFAULT_DISAGREEMENT_THRESHOLD = 0.1

# The auto-judge lifecycle states. ENABLED is reachable ONLY through the Q11 gate
# (`enablement.enable_autojudge`); the disagreement trigger and the AMBIGUOUS trigger
# drive the single reverse transition to DISABLED_REQUIRE_HUMAN, never forward.
STATE_DISABLED_INITIAL = "DISABLED_INITIAL"
STATE_ENABLED = "ENABLED"
STATE_DISABLED_REQUIRE_HUMAN = "DISABLED_REQUIRE_HUMAN"

# `11` §5-Q11 order: (1) human labels -> (2) success criteria in prose -> (3) VLM
# precision/recall measured against those labels -> (4) then decide enablement. The
# stages are ordered; a later stage cannot be satisfied while an earlier one is not
# (criteria need labels; precision/recall needs criteria). `enablement` enforces both
# the completeness and the order.
Q11_STAGE_HUMAN_LABELS = "human_labels_collected"
Q11_STAGE_SUCCESS_CRITERIA = "success_criteria_defined"
Q11_STAGE_PRECISION_RECALL = "precision_recall_measured"
Q11_ORDER = (
    Q11_STAGE_HUMAN_LABELS,
    Q11_STAGE_SUCCESS_CRITERIA,
    Q11_STAGE_PRECISION_RECALL,
)

# `FR-SIM-095`: the evaluation critic is Cosmos Reason 2, which runs only on a
# Hopper- or Blackwell-class GPU. The preflight compares that requirement against the
# owned fleet (`02c` §2.4 DeploymentTarget). These are the architecture generations
# the preflight distinguishes; only the two named here clear the requirement.
ARCH_AMPERE = "ampere"
ARCH_HOPPER = "hopper"
ARCH_BLACKWELL = "blackwell"

# The model name the sidecar records so a model-judged label is attributable to the
# judge that produced it. The real run is DEFERRED; this is the identity the adapter
# stamps, not evidence a run happened.
COSMOS_REASON_2 = "cosmos-reason-2"

# The disagreement histogram key for a disagreeing pair that carries no human failure
# tag (a human-success / model-failure disagreement — the VLM under-called success).
# Named so those disagreements are visible in `disagreement_by_tag` rather than
# silently dropped from a tag-keyed histogram.
DISAGREEMENT_NO_TAG = "(no-failure-tag)"
