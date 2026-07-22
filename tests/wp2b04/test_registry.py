"""The payload registry and value validation: a mis-registration cannot exist or persist.

An accepted out-of-band or units-error payload is the FAIL_BLOCKING case (a constant residual
offset). These tests hold the two guards that stop it: the `Payload` value refuses to
construct outside the 0-6.0 kg band or with a units-error CoG, and the registry is a
single-payload store whose register/unregister the gravity model reads.
"""

from __future__ import annotations

import pytest

from backend.payload import (
    PAYLOAD_MASS_MAX_KG,
    PAYLOAD_MASS_NOMINAL_KG,
    Payload,
    PayloadError,
    PayloadRegistry,
)


def test_nominal_and_peak_masses_construct() -> None:
    # The rated nominal and the peak ceiling are both inside the band (FR-SAF-036).
    assert Payload.at_mount(PAYLOAD_MASS_NOMINAL_KG, "nominal").mass_kg == PAYLOAD_MASS_NOMINAL_KG
    assert Payload.at_mount(PAYLOAD_MASS_MAX_KG, "peak").mass_kg == PAYLOAD_MASS_MAX_KG
    assert Payload.at_mount(0.0, "bare").mass_kg == 0.0


def test_mass_above_peak_is_refused() -> None:
    # A mass over 6.0 kg is a mis-registration, refused at construction, not silently accepted.
    with pytest.raises(PayloadError, match="outside the registry band"):
        Payload.at_mount(PAYLOAD_MASS_MAX_KG + 0.1, "over")


def test_negative_mass_is_refused() -> None:
    with pytest.raises(PayloadError, match="outside the registry band"):
        Payload.at_mount(-0.1, "negative")


def test_nonfinite_mass_is_refused() -> None:
    with pytest.raises(PayloadError, match="outside the registry band"):
        Payload.at_mount(float("nan"), "nan")


def test_units_error_cog_is_refused() -> None:
    # A CoG a metre out (e.g. millimetres entered as metres) is a data-entry error, refused.
    with pytest.raises(PayloadError, match="units-error sanity ceiling"):
        Payload.from_cog(2.0, (0.0, 0.0, -1.0), "bad-cog")


def test_nonfinite_cog_is_refused() -> None:
    with pytest.raises(PayloadError, match="non-finite or beyond"):
        Payload.from_cog(2.0, (0.0, float("inf"), 0.0), "inf-cog")


def test_cog_wrong_width_is_refused() -> None:
    with pytest.raises(PayloadError, match="3 components"):
        Payload.from_cog(2.0, (0.0, 0.0), "short-cog")


def test_registry_register_and_unregister() -> None:
    registry = PayloadRegistry()
    assert registry.current() is None
    assert not registry.is_registered()

    payload = Payload.at_mount(3.0, "tool")
    registry.register(payload)
    assert registry.is_registered()
    assert registry.current() is payload

    registry.unregister()
    assert registry.current() is None
    assert not registry.is_registered()


def test_registry_register_replaces_previous() -> None:
    # One end-effector: registering replaces rather than accumulates.
    registry = PayloadRegistry()
    registry.register(Payload.at_mount(2.0, "first"))
    second = Payload.at_mount(4.0, "second")
    registry.register(second)
    assert registry.current() is second
