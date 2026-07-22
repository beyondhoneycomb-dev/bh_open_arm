"""WP-2B-07 — the friction least-squares identification (PG-FRIC-001, spec 04 FR-MAN-034/035).

Wave 2B's third sequential package. It cross-checks WP-2B-06's excitation logs against
WP-2B-02's gravity term to fit the four-term tanh friction law
`tau_fric(omega) = Fo + Fv*omega + Fc*tanh(k_eff*omega)` per joint, and writes it to the
`friction.yaml` the upstream leaves empty. What runs here (offline, on synthetic logs) and what
is deferred (a real PG-FRIC-001 pass) are kept strictly apart — the writer cannot emit a pass,
and the deferral ships a real-fixture re-verification hook.

The public surface:

* `FrictionParams` / `identify_friction` / `fit_joint` — the model and the scipy least-squares
  fit. `FrictionParams` stores `k_eff` and exposes the YAML `k = k_eff / K_EFF_SCALE`.
* `InverseDynamicsBasis` — `M*qdd + C*qd + g` from the committed v2 model, consuming WP-2B-02
  for gravity/Coriolis and adding only the inertia term; the thing subtracted to expose
  friction, never a function of the friction result.
* `separation_stats` / `SeparationStat` — the residual-separation evidence (acceptance ①).
* `identification_band` / `band_from_identification` — the band as a function of the logging
  frequency (acceptance ③).
* `V1_SEED_FRICTION` / `relative_error_table` — the per-joint comparison to the v1 seed
  (acceptance ④).
* `generate_synthetic_log` — the synthetic excitation log (known friction, real v2 dynamics).
* `write_identified_friction` / `build_friction_document` — the friction.yaml writer, carrying
  the `k_eff = 0.1 * k` convention (acceptance ②) and the always-provisional status.
* `reverify_from_fixture` — the deferred real-pass re-verification hook.
"""

from __future__ import annotations

from backend.friction.band import (
    IdentificationBand,
    band_from_identification,
    identification_band,
)
from backend.friction.basis import DynamicsComponents, InverseDynamicsBasis
from backend.friction.constants import (
    FIXTURE_ENV_VAR,
    K_EFF_SCALE,
    LOG_FREQ_REFERENCE_HZ,
)
from backend.friction.errors import FrictionIdentificationError
from backend.friction.identify import (
    IdentificationResult,
    JointFit,
    fit_joint,
    identify_friction,
)
from backend.friction.log import ExcitationLog
from backend.friction.model import FrictionParams
from backend.friction.reverify import (
    RealFrictionVerification,
    fixture_dir_from_env,
    reverify_from_fixture,
)
from backend.friction.seed import (
    V1_SEED_FRICTION,
    RelativeError,
    format_relative_error_table,
    relative_error_table,
)
from backend.friction.separation import (
    SeparationStat,
    format_separation_table,
    separation_stats,
)
from backend.friction.synthetic import (
    SyntheticLog,
    default_truth,
    generate_synthetic_log,
)
from backend.friction.writer import (
    build_friction_document,
    friction_yaml_text,
    write_friction_yaml,
    write_identified_friction,
)

__all__ = [
    "FIXTURE_ENV_VAR",
    "K_EFF_SCALE",
    "LOG_FREQ_REFERENCE_HZ",
    "V1_SEED_FRICTION",
    "DynamicsComponents",
    "ExcitationLog",
    "FrictionIdentificationError",
    "FrictionParams",
    "IdentificationBand",
    "IdentificationResult",
    "InverseDynamicsBasis",
    "JointFit",
    "RealFrictionVerification",
    "RelativeError",
    "SeparationStat",
    "SyntheticLog",
    "band_from_identification",
    "build_friction_document",
    "default_truth",
    "fit_joint",
    "fixture_dir_from_env",
    "format_relative_error_table",
    "format_separation_table",
    "friction_yaml_text",
    "generate_synthetic_log",
    "identification_band",
    "identify_friction",
    "relative_error_table",
    "reverify_from_fixture",
    "separation_stats",
    "write_friction_yaml",
    "write_identified_friction",
]
