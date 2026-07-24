// Dataset-screen command intents (WP-G-S08). The screen is a FACADE: it SENDS
// operator intent to the backend-owned dataset engine (WP-3D-01..05) and performs no
// transformation itself. Two invariants are structural in the op set below:
//
//   - Every edit is copy-on-write (CG-G-S08f): the one edit op, `cow_edit`, always
//     carries an `outputRepoId` — the backend-stamped NEW dataset the edit writes to.
//     There is no in-place op, no op that names the source as its own output, and no
//     `overwrite` flag. Even an upstream in-place operation (modify_tasks) is copied
//     first by the engine, so at this boundary every edit produces a new dataset.
//   - There is no export / convert / import / hub-upload op (CG-G-S08e): the platform
//     is LeRobot v3.0 native and format conversion is blocked (WP-3D-07). No op here
//     leaves the native format or crosses the air gap.
//
// The screen never stamps a repo_id itself (that is the backend's `stamp_repo_id()`);
// the `outputRepoId` it sends comes from the backend edit preview.

// Select which dataset the episode / signals / verification views show.
export interface SelectDatasetCommand {
  op: "select_dataset";
  stampedRepoId: string;
}

// Select which episode of the current dataset the scrubber, plot and camera sync show.
export interface SelectEpisodeCommand {
  op: "select_episode";
  episodeIndex: number;
}

// Run a previewed copy-on-write edit. `outputRepoId` is the backend-stamped NEW
// dataset the result is written to — the source is never mutated (CG-G-S08f). The
// backend engine copies first (for an in-place upstream op) and performs the
// transformation; the screen only asks for it.
export interface CowEditCommand {
  op: "cow_edit";
  operation: string;
  sourceRepoId: string;
  outputRepoId: string;
}

// Attach a human success/fail verdict to an episode's label sidecar (WP-3B-12). The
// backend's label store applies it with `with_manual`, preserving any auto suggestion;
// the screen sends the verdict and renders the stored label, never fabricating one.
export interface SetVerdictCommand {
  op: "set_verdict";
  episodeIndex: number;
  verdict: "success" | "fail";
}

export type DatasetCommand =
  | SelectDatasetCommand
  | SelectEpisodeCommand
  | CowEditCommand
  | SetVerdictCommand;

// The sink a screen publishes intents to. In production this wraps the single WS
// client's control-frame send (WP-G-01), where the server accepts or refuses by
// lease/role — the browser never decides. The default is a no-op so the AI-offline
// lane drives the screen without a backend.
export interface DatasetCommandSink {
  send(command: DatasetCommand): void;
}

export const noopCommandSink: DatasetCommandSink = {
  send: () => {},
};

// Project a command intent onto the frozen CTR-WS command frame body. Kept separate
// from the sink so the wire shape is testable without a socket.
export function commandToWire(command: DatasetCommand): Record<string, unknown> {
  return { type: "command", ...command };
}
