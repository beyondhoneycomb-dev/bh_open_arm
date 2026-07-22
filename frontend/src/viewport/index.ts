// Public surface of the WP-G-02 viewport subtree. WP-G-00's /viewport route (and
// any screen embedding the shared viewport) imports the panel and canvas from
// here; the pure logic modules are re-exported for screen WPs that need the gates
// (asset block, snapshot acceptance, stream-age gating) without the DOM.

export { ViewportPanel } from "./ViewportPanel";
export { ViewportCanvas } from "./ViewportCanvas";

export { evaluateAsset, type AssetProvenance, type AssetDecision } from "./loader/provenance";
export { validateUrdfSource, type UrdfSourceResult } from "./loader/urdfSource";
export { acceptSnapshot, type JointFrame, type SnapshotResult } from "./state/jointSnapshot";
export { evaluateStreamAge, controlInputAllowed, type StreamAgeState } from "./state/streamAge";
export { resolvePublishRate, type PublishRateResult } from "./state/publishRate";
export { reconcileEndEffector, type EePose } from "./state/fkReconcile";
export { collisionCoverage, hasCollisionGaps, type CollisionCoverage } from "./scene/collisionModel";
export { rosToThreeQuaternion, transformRosPoint, applyWorldFrame } from "./scene/coordinateTransform";
export { type RenderMode, type LayerState } from "./scene/layers";
export { defaultViewportSource, type ViewportSource } from "./viewportSource";
