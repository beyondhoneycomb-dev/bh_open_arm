// Viewport-wide constants (WP-G-02). Every literal that carries meaning in the
// viewport's logic is named here so the one place a value is decided is findable:
// the world-frame rotation, the stream-stale threshold, the publish-rate default
// and cap, the mesh-extension allowlist, the EE reconciliation tolerance.

// ROS-to-Three world-frame rotation. ROS is Z-up (X forward, Z up); Three.js is
// Y-up. Rotating the robot root -90 degrees about X carries ROS +Z (up) onto
// Three +Y (up), so the robot renders upright (CG-G-02c). This is the ONE
// coordinate transform the browser owns — a rendering rotation, not a physical
// unit. Angle/unit conversion between deg and rad is the backend's alone
// (CTR-UNIT@v1); the viewport never performs it (CG-G-02a).
export const ROS_TO_THREE_ROTATION_X = -Math.PI / 2;

// Stream age beyond this (milliseconds) marks the view stale and blocks every
// control input (CG-G-02e). A frame older than several control periods is no
// longer a truthful picture of the arm, and drawing it as live invites commands
// against a pose that has moved on. NFR-GUI-003 sets the live-view intent; the
// binding number is fixed by measurement later (I-6), this is the working value.
export const STREAM_STALE_AGE_MS = 250;

// Telemetry publish rate (CG-G-02i): 30 Hz by default, hard cap 60 Hz. A request
// above the cap is rejected, not silently clamped, so an over-configuration is
// surfaced rather than absorbed.
export const PUBLISH_RATE_DEFAULT_HZ = 30;
export const PUBLISH_RATE_MAX_HZ = 60;

// Mesh file extensions the URDF loader will accept from the backend (CG-G-02h).
// Anything else is rejected before a fetch is attempted. Lowercase, no dot.
export const MESH_EXTENSION_ALLOWLIST = ["stl", "dae", "obj"] as const;
export type AllowedMeshExtension = (typeof MESH_EXTENSION_ALLOWLIST)[number];

// EE-pose agreement tolerance (metres) between the browser's auxiliary FK and the
// backend MJCF FK. The backend value is the sole canon (CG-G-02f); a disagreement
// beyond this raises a warning only — the browser never substitutes its own EE
// number, because the thing that makes the command is the backend MJCF FK.
export const EE_FK_TOLERANCE_M = 0.005;

// The point-cloud layer is gone, not hidden: PG-DEPTH-001 accepts an RGB-only
// reduction, so the depth source does not exist. Its absence is a standing fact
// the viewport states rather than a defect it works around (WP-G-02 negative
// branch). No point-cloud toggle is offered anywhere in the viewport.
export const POINTCLOUD_LAYER_AVAILABLE = false;
export const POINTCLOUD_REDUCTION_NOTICE =
  "포인트클라우드 레이어 없음 — RGB-only 축소(PG-DEPTH-001), 뎁스 소스 부재";
