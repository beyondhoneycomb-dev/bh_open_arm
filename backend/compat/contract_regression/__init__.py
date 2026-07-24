"""WP-4B-05 — LeRobot contract-regression registration for the 4A/4B band.

`02c` §2.5 / `FR-OPS-089`: a LeRobot upgrade may deploy only after the contract
regression passes. This package registers the internal LeRobot facts the 4A/4B
deliverables depend on *through the Wave 0-Env checker's own API* (`registry.env.
upstream`) and never edits the checker file. The deliverable is registration data
plus the thin module that injects it, not a second checker.

Public surface:
- `predicates.ADDITIONAL_PREDICATES` — the predicates this band adds.
- `register.run()` — register the predicates and run base + additional facts through
  the checker; the verdict blocks deployment on any drift.
- `ghost_version.check_ghost_version()` — the CG-4B-05c SHA-pin / ghost-version guard.
- `cli.main()` — the deployment gate combining both.
"""
