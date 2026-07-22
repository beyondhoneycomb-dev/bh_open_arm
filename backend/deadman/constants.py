"""Named parameters of the deadman lease (`WP-2A-02`, U-4).

Every threshold the lease logic depends on is named here rather than buried at a
call site. The lease *duration* itself is not re-declared: it is reused from the
actuation spine (`backend.actuation.config.LEASE_DURATION_SEC`), because the
scheduler that reads `LeaseManager.is_expired` and this package that renews the
same `LeaseManager` must agree on one duration or the deadman splits into two
truths — exactly the failure this WP exists to prevent.
"""

from __future__ import annotations

from backend.actuation.config import LEASE_DURATION_SEC

# The lease duration this package renews against, reused from the actuation spine.
# A renewal accepted at server time `t` sets expiry to `t + LEASE_DURATION_SEC` on
# the server clock; the scheduler's `LeaseManager` measures expiry against the same
# value, so there is one duration, not two.
DEADMAN_LEASE_DURATION_SEC = LEASE_DURATION_SEC

# Maximum age of an accepted renewal, measured on the server clock against the
# client's issue time mapped into the server frame. `02b` §1.0 fixes it as a
# function of the lease period, defaulting to one times that period. A renewal
# older than this is discarded on arrival and does not extend the lease — a
# delayed message is invalid, not "late but valid".
# Defaulting to one lease duration is the conservative upper bound: a renewal older
# than the whole lease it would grant is unambiguously stale. Deployments with a
# known, tighter renewal cadence pass a smaller value.
DEFAULT_MAX_LEASE_AGE_SEC = LEASE_DURATION_SEC

# The lease generation live at torque-on. The initial "take the deadman" (first
# renewal under this generation) needs no re-arm handshake — there is no prior
# latch to clear. Every generation after this one is minted only by the server's
# re-arm handshake (`RearmHandshake`), never asserted by a client.
INITIAL_LEASE_GENERATION = 0

# Latch attribution for a deadman expiry, carried in the `ops.cancel` `LatchReason`
# so the audit can tell a deadman-expiry latch from a collision or ERR-nibble latch.
DEADMAN_LATCH_GATE_ID = "DEADMAN"
DEADMAN_LATCH_PREVIOUS_STATE = "LIVE"
DEADMAN_LATCH_NEW_STATE = "LATCHED"
