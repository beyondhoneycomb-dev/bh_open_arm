// Collision coverage (CG-G-02g). Collision mode compares the links the loaded
// URDF declares against the links `collisions.yaml` gives a collision geom. A link
// present in the URDF but absent from collisions.yaml has NO collision geometry —
// most consequentially link7, whose absence means the end effector is invisible
// to self-collision checks. Collision mode must show that gap, not draw the link
// as though it were covered. The viewport does not repair the gap or invent a
// geom (that is the backend's collision-preflight variant); it makes the omission
// visible so it cannot pass as fine.
//
// Both link sets are inputs derived at runtime — the URDF link set from the loaded
// robot, the declared set from collisions.yaml — so this module hardcodes neither.

export interface CollisionCoverage {
  // Links the URDF declares (the reference set the coverage is judged against).
  readonly urdfLinks: readonly string[];
  // Links collisions.yaml actually gives a collision geom.
  readonly declaredLinks: readonly string[];
  // URDF links with no collision entry — the gaps Collision mode surfaces.
  readonly missing: readonly string[];
}

export function collisionCoverage(
  urdfLinks: readonly string[],
  declaredCollisionLinks: readonly string[],
): CollisionCoverage {
  const declared = new Set(declaredCollisionLinks);
  const missing = urdfLinks.filter((link) => !declared.has(link));
  return { urdfLinks, declaredLinks: declaredCollisionLinks, missing };
}

export function hasCollisionGaps(coverage: CollisionCoverage): boolean {
  return coverage.missing.length > 0;
}
