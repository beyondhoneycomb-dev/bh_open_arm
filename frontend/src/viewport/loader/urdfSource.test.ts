// CG-G-02h: a URDF whose meshes still carry package:// (backend did not rewrite)
// is rejected, and so are external origins and out-of-allowlist mesh extensions.

import { describe, expect, it } from "vitest";

import { validateUrdfSource } from "./urdfSource";

describe("CG-G-02h URDF source validation", () => {
  it("accepts a backend-served URDF with STL/DAE/OBJ meshes", () => {
    const result = validateUrdfSource("/assets/robot/openarm.urdf", [
      "/assets/robot/link1.stl",
      "/assets/robot/link2.dae",
      "/assets/robot/link3.obj",
    ]);
    expect(result.ok).toBe(true);
  });

  it("rejects an un-rewritten package:// mesh reference", () => {
    const result = validateUrdfSource("/assets/robot/openarm.urdf", [
      "package://openarm_description/meshes/link1.stl",
    ]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("unrewritten-package-uri");
    }
  });

  it("rejects a URDF served from an external origin", () => {
    const result = validateUrdfSource("https://cdn.example.com/openarm.urdf", []);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("external-origin");
    }
  });

  it("rejects a mesh served from an external origin", () => {
    const result = validateUrdfSource("/assets/robot/openarm.urdf", [
      "https://cdn.example.com/link1.stl",
    ]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("external-origin");
    }
  });

  it("rejects a mesh whose extension is not in the allowlist", () => {
    const result = validateUrdfSource("/assets/robot/openarm.urdf", ["/assets/robot/link1.png"]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("mesh-extension-not-allowed");
    }
  });
});
