// Display-severity classifier for a backend collision contact. MuJoCo has
// already decided the contact exists — SAF owns the check (12 §2.11:
// data.ncon / data.contact[i]) and reports each contact's signed penetration
// depth `dist` and its collision margin. This module reads those backend
// numbers and picks a HIGHLIGHT class for intrusion vs imminent (CG-G-S12e).
//
// It performs no geometry: no distance computation, no intersection test, no
// wall-vs-arm math. Comparing the sign of a value the backend already produced
// is not a collision decision, so CG-G-S12d (zero self-collision decision in the
// GUI) stays intact.

export type ContactSeverity = "intrusion" | "imminent" | "clear";

// `dist` is MuJoCo's signed gap in meters: negative means the geoms already
// penetrate (intrusion); a non-negative gap within the backend margin means an
// approach inside the safety envelope (imminent); beyond the margin is clear
// (§2.11, FR-SAF-011). `margin` is the backend's own contact margin, never a GUI
// constant.
export function contactSeverity(distMeters: number, marginMeters: number): ContactSeverity {
  if (distMeters < 0) {
    return "intrusion";
  }
  if (distMeters <= marginMeters) {
    return "imminent";
  }
  return "clear";
}

// Whether a severity warrants a highlight (both intrusion and imminent do).
export function isHighlighted(severity: ContactSeverity): boolean {
  return severity !== "clear";
}

export const SEVERITY_LABELS: Readonly<Record<ContactSeverity, string>> = {
  intrusion: "침범",
  imminent: "임박",
  clear: "여유",
};
