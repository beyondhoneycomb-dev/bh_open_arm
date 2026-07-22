// Asset provenance and the version gate (CG-G-02b). Every URDF the viewport loads
// is stamped by the backend with where it came from and which robot generation it
// describes. The viewport records that stamp unconditionally and blocks any asset
// whose robot_version is not the one the backend declares current: a v1 asset
// (robot_version "1.0") differs from v2 only by the j2 limit, so it loads without
// error and renders a wrong workspace silently. Blocking is the defence, and the
// recorded provenance is what tells the operator which stale asset was served.
//
// The accepted version is NOT a constant this module invents. The backend owns
// which generation is current (backend.seed_profile enforces "2.0"); the viewport
// is a window that compares the served stamp against the backend-declared accept
// value. Field names are snake_case to match the backend provenance JSON verbatim.

export interface AssetProvenance {
  readonly source_repo: string;
  readonly commit_sha: string;
  readonly robot_version: string;
}

export interface AssetDecision {
  // Whether the load is blocked. A blocked asset is never handed to the loader.
  readonly blocked: boolean;
  // The provenance is recorded whether or not the asset is blocked, so a blocked
  // load still shows which asset (and which generation) the backend served.
  readonly provenance: AssetProvenance;
  // Human-readable cause when blocked; null when the asset is accepted.
  readonly reason: string | null;
}

// Decide whether an asset may load. `acceptedRobotVersion` comes from the backend
// (its asset manifest), never from a browser-side constant.
export function evaluateAsset(
  provenance: AssetProvenance,
  acceptedRobotVersion: string,
): AssetDecision {
  if (provenance.robot_version !== acceptedRobotVersion) {
    return {
      blocked: true,
      provenance,
      reason: `asset is robot_version ${provenance.robot_version}, backend accepts ${acceptedRobotVersion}`,
    };
  }
  return { blocked: false, provenance, reason: null };
}
