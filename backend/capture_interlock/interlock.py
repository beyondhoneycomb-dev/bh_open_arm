"""The source-delete interlock — the one gate that may delete a raw capture source.

The raw source is deleted only when both hold: the converted dataset certifies READY
through the committed WP-3D-05 verifier (`ensure_training_ready`, imported, never
reimplemented), and all four capture-preservation checks pass for every episode. Any
mismatch preserves the original and flags the offending episode; nothing is deleted.
A delete requested against an uncertified source raises `CaptureInterlockError`
rather than executing — the runtime form of the `FAIL_BLOCKING` branch, because a
delete with any check unmet is irreversible data loss (`02b` §7.2 WP-3C-06).

The delete happens in exactly one place, `delete_certified`, guarded on the decision;
there is no other code path from this band to `CaptureSource.delete`, so the
interlock is structural rather than a discipline a caller must remember.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.capture_interlock.constants import (
    FLAG_DIR,
    FLAG_SIDECAR_TEMPLATE,
    REQUIRED_CAPTURE_CHECKS,
    VERDICT_MISMATCH,
)
from backend.capture_interlock.converted import ConvertedDataset
from backend.capture_interlock.preservation import check_episode
from backend.capture_interlock.report import (
    CaptureInterlockError,
    DeleteDecision,
    DeleteOutcome,
    EpisodePreservation,
    failed,
)
from backend.capture_interlock.source import CaptureSource, CaptureSourceError
from backend.dataset.integrity import IntegrityError, ensure_training_ready
from backend.dataset.viewer.layout import DatasetLayoutError

_READY_OK = "converted dataset verified READY (all WP-3D-05 checks passed)"


class SourceDeleteInterlock:
    """Decides whether a raw capture source may be deleted, and performs the delete.

    Ownership: stateless; every method takes the raw and converted roots it acts on.
    The decision combines the committed WP-3D-05 READY gate with this band's four
    capture-preservation checks, and the delete is impossible without a DELETABLE
    decision.
    """

    def decide(
        self,
        raw_root: Path,
        converted_root: Path,
        recorded_stats_hash: str | None = None,
    ) -> DeleteDecision:
        """Judge whether the raw source may be deleted, checking every episode.

        Args:
            raw_root: The raw capture source root.
            converted_root: The converted dataset root.
            recorded_stats_hash: An explicit stats hash for the WP-3D-05 stats-hash
                check; when None it falls back to `info.json`'s recorded value.

        Returns:
            (DeleteDecision) The READY verdict, per-episode preservation results, and
                whether the source is DELETABLE.
        """
        raw_root = Path(raw_root)
        converted_root = Path(converted_root)

        training_ready, ready_detail = self._verify_ready(converted_root, recorded_stats_hash)
        episodes = self._check_all_episodes(raw_root, converted_root)

        return DeleteDecision(
            raw_root=str(raw_root),
            converted_root=str(converted_root),
            training_ready=training_ready,
            ready_detail=ready_detail,
            episodes=episodes,
        )

    def delete_certified(self, source: CaptureSource, decision: DeleteDecision) -> None:
        """Delete the raw source, but only for a DELETABLE decision.

        This is the single deletion point in the band. It refuses — by raising —
        any decision that is not DELETABLE, so a delete can never fire with a READY
        failure or a preservation mismatch unresolved.

        Args:
            source: The raw source to delete.
            decision: The decision authorising the delete.

        Raises:
            CaptureInterlockError: When the decision is not DELETABLE.
        """
        if not decision.deletable:
            raise CaptureInterlockError(
                f"refusing to delete {source.root}: decision is {decision.verdict}; "
                + "; ".join(decision.refusal_reasons())
            )
        source.delete()

    def delete_if_certified(
        self,
        raw_root: Path,
        converted_root: Path,
        recorded_stats_hash: str | None = None,
    ) -> DeleteOutcome:
        """Decide and, only if certified, delete the raw source; else preserve + flag.

        On a DELETABLE decision the raw source is removed. On a REFUSED decision the
        raw source is left untouched (zero deletion) and every mismatched episode is
        flagged in the converted dataset's meta tree.

        Args:
            raw_root: The raw capture source root.
            converted_root: The converted dataset root.
            recorded_stats_hash: An explicit stats hash for the WP-3D-05 check.

        Returns:
            (DeleteOutcome) The decision, whether the source was deleted, and the
                flagged episodes.
        """
        decision = self.decide(raw_root, converted_root, recorded_stats_hash)
        if decision.deletable:
            self.delete_certified(CaptureSource(raw_root), decision)
            return DeleteOutcome(decision=decision, deleted=True, flagged_episodes=())

        flagged = self._flag_mismatched_episodes(Path(converted_root), decision)
        return DeleteOutcome(decision=decision, deleted=False, flagged_episodes=flagged)

    def _verify_ready(
        self, converted_root: Path, recorded_stats_hash: str | None
    ) -> tuple[bool, str]:
        """Run the committed WP-3D-05 READY gate, capturing its verdict as data.

        Returns:
            (tuple[bool, str]) Whether the dataset is READY, and a detail string —
                the confirmation on READY, the INVALID reasons on failure.
        """
        try:
            ensure_training_ready(converted_root, recorded_stats_hash)
        except IntegrityError as bad:
            return False, str(bad)
        except (DatasetLayoutError, FileNotFoundError, ValueError) as bad:
            return False, f"converted dataset could not be verified: {bad}"
        return True, _READY_OK

    def _check_all_episodes(
        self, raw_root: Path, converted_root: Path
    ) -> tuple[EpisodePreservation, ...]:
        """Run the four preservation checks for every raw-source episode.

        Every episode is auto-checked (`02b` §7.2 WP-3C-06 ⑥). A converted dataset
        that cannot even be opened yields no per-episode results — the READY gate has
        already refused it, and the empty episode set refuses the delete on its own.
        """
        source = CaptureSource(raw_root)
        try:
            converted = ConvertedDataset(converted_root)
        except DatasetLayoutError:
            return ()

        episodes: list[EpisodePreservation] = []
        for episode_index in source.episode_indices():
            try:
                source_episode = source.episode(episode_index)
            except CaptureSourceError as bad:
                episodes.append(
                    EpisodePreservation(
                        episode_index=episode_index,
                        results=tuple(
                            failed(name, f"raw source unreadable: {bad}")
                            for name in REQUIRED_CAPTURE_CHECKS
                        ),
                    )
                )
                continue
            episodes.append(check_episode(source_episode, converted))
        return tuple(episodes)

    def _flag_mismatched_episodes(
        self, converted_root: Path, decision: DeleteDecision
    ) -> tuple[int, ...]:
        """Write a mismatch flag into the converted dataset for each MISMATCH episode.

        The flag is a small JSON file under the converted dataset's `meta/capture/
        flags/` tree — a runtime data artifact, never a write to the raw source,
        which stays byte-for-byte intact. Episodes that passed all four checks are
        not flagged even when the delete is refused for a READY failure.

        Returns:
            (tuple[int, ...]) The episode indices that were flagged.
        """
        flag_dir = converted_root / FLAG_DIR
        flagged: list[int] = []
        for episode in decision.episodes:
            if episode.preserved:
                continue
            flag_dir.mkdir(parents=True, exist_ok=True)
            path = converted_root / FLAG_SIDECAR_TEMPLATE.format(
                episode_index=episode.episode_index
            )
            path.write_text(
                json.dumps(
                    {
                        "episode_index": episode.episode_index,
                        "verdict": VERDICT_MISMATCH,
                        "reasons": list(episode.reasons()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            flagged.append(episode.episode_index)
        return tuple(flagged)
