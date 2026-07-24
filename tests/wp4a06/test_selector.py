"""CG-4A-06a — `.pos` selection is name-derived, invariant under names rotation.

`02c` §1.6 ①: a rotated `names` order must still select the EXACT same `.pos`
channel set (`10` FR-TRN-063). The discriminating control is a positional selector,
which picks a different physical set under rotation — proving these tests would fail
a regression to positional slicing rather than pass vacuously.
"""

from __future__ import annotations

from backend.training.projection import (
    ProjectionKind,
    observation_projection_indices,
    select_pos_indices,
)
from contracts.recorder import POSITION_SUFFIX, action_names
from tests.wp4a06.fixtures import observation_names, rotated

# The per-motor interleave stride: each motor contributes (.pos, .vel, .torque), so
# a naive "the .pos channels are every third index" positional slice starts at 0
# with this stride. It is correct ONLY in canonical order — the exact assumption
# `10` FR-TRN-063 forbids, used here purely as the discriminating negative control.
_INTERLEAVE_STRIDE = 3


def _channel_set(names: tuple[str, ...], indices: list[int]) -> frozenset[str]:
    """Return the set of channel names an index list selects."""
    return frozenset(names[index] for index in indices)


def test_pos_selection_invariant_under_rotation() -> None:
    """The selected `.pos` channel SET is identical for every names rotation."""
    names = observation_names()
    canonical = _channel_set(names, select_pos_indices(names))
    assert len(canonical) == len(names) // _INTERLEAVE_STRIDE
    for by in range(1, len(names)):
        turned = rotated(names, by)
        assert _channel_set(turned, select_pos_indices(turned)) == canonical


def test_positional_slice_would_break_under_rotation() -> None:
    """A positional stride selects a DIFFERENT set once rotated — the control fires."""
    names = observation_names()
    canonical = _channel_set(names, select_pos_indices(names))
    positional = list(range(0, len(names), _INTERLEAVE_STRIDE))
    # In canonical order the stride happens to hit the .pos channels...
    assert _channel_set(names, positional) == canonical
    # ...but after a one-channel rotation it points at a different physical set,
    # which is exactly the silent corruption a name-derived selection avoids.
    turned = rotated(names, 1)
    assert _channel_set(turned, positional) != canonical


def test_selected_channels_all_carry_pos_suffix() -> None:
    """Every selected observation channel ends with `.pos`, never `.vel`/`.torque`."""
    names = observation_names()
    for index in select_pos_indices(names):
        assert names[index].endswith(POSITION_SUFFIX)


def test_select_pos_indices_on_action_names_is_full_set() -> None:
    """The same extractor runs on `action` names, which are already all `.pos`."""
    targets = action_names(bimanual=True)
    indices = select_pos_indices(targets)
    assert indices == list(range(len(targets)))


def test_full_projection_keeps_every_channel() -> None:
    """FULL keeps all channels; POS_ONLY keeps only the `.pos` subvector."""
    names = observation_names()
    assert observation_projection_indices(names, ProjectionKind.FULL) == list(range(len(names)))
    assert observation_projection_indices(names, ProjectionKind.POS_ONLY) == select_pos_indices(
        names
    )
