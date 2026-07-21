"""Wave -1 normalization ledger: schema, loader, validator, and seeder hook.

The ledger (`docs/plan/normalization/ledger.yaml`) records how each specification
contradiction of `02a` §1.3 was resolved — which id survives, which text is
discarded, and the executable check that keeps the ruling from eroding. This
package owns the machinery that loads and validates it; `WP-N1-02` owns the data.

The discarded entries are safety requirements (`NORM-006` splits 비상정지 into
`STOP_HOLD`/`POWER_CUT`; `NORM-007` removes a power-cut path the rig has no
hardware for), so a discarded quote is checked character-exact against its source
and never paraphrased.
"""
