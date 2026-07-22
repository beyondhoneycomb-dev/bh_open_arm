// Side selection gate (CG-G-S02a). With no `side` chosen the backend silently
// locks every joint limit to a ±5° band and clips motion with NO error raised
// (02 §2.0.3 F-6'). Because nothing downstream complains, THIS SCREEN IS THE ONLY
// DEFENCE: it must refuse to let bringup proceed until a side is picked. The
// module owns only the gate — it does not apply the clamp, which is the backend's.

// The follower sides the backend recognises (02 §2.1, config side="left"/"right"),
// plus the bimanual selection that arms both followers. `null` is "unchosen".
export const ARM_SIDES = ["left", "right", "bimanual"] as const;
export type ArmSide = (typeof ARM_SIDES)[number];
export type SideSelection = ArmSide | null;

export const ARM_SIDE_LABELS: Record<ArmSide, string> = {
  left: "왼팔 (left)",
  right: "오른팔 (right)",
  bimanual: "양팔 (bimanual)",
};

// Whether bringup may proceed. False exactly when no side is chosen — the single
// question the bringup and profile controls ask before enabling themselves.
export function canProceedWithSide(side: SideSelection): side is ArmSide {
  return side !== null;
}

// The follower sides a selection arms. A bimanual selection arms both; a single
// side arms itself. Used to filter the profiles and joints shown, never to decide
// limits (the backend owns limits).
export function followerSidesFor(side: ArmSide): readonly ("left" | "right")[] {
  if (side === "bimanual") {
    return ["left", "right"];
  }
  return [side];
}
