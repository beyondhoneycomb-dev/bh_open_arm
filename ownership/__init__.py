"""CTR-OWN@v1 — the file/module ownership registry and the fan-out width prover.

`WP-0A-03`. This package formalises the ownership discipline every prior wave
declared inline: it reads *who owns what* from the registry `owns[]` axis and
*when* (the handover order) from `06` §3.2, joins them into the CTR-OWN@v1 span
view, and proves the overlap-0 property that lets a `SHAPE-IM` fan-out width `n`
be more than the assumed `1`.

Modules:
    model: the span/claim/conflict data model.
    prover: reads the two sources; the overlap checker and width calculator.
    contract: loads `ownership/registry.yaml` and drift-checks it against §3.2.
    cli: the ownership-verification job (`python -m ownership.cli`).
"""
