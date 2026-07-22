// URDF source validation (CG-G-02h, air-gap). The viewport loads a robot only
// from a backend-served URL: the backend expands xacro to URDF, pre-rewrites
// every `package://` reference to a served path, and serves the meshes. Three
// things get an asset rejected before any fetch is attempted:
//
//   - an external-origin URL (the asset must be same-origin/backend-served, so a
//     scheme://host URL is off-origin and fails the air-gap);
//   - an un-rewritten `package://` reference (the backend did not rewrite it, so
//     the browser cannot resolve it and must not guess an origin);
//   - a mesh whose extension is not in the STL/DAE/OBJ allowlist.
//
// Rejecting up front keeps a malformed asset from reaching urdf-loader, where a
// failed sub-fetch would render a half-built robot rather than an honest refusal.

import { MESH_EXTENSION_ALLOWLIST } from "../constants";

export type UrdfRejectReason =
  | "external-origin"
  | "unrewritten-package-uri"
  | "mesh-extension-not-allowed";

export type UrdfSourceResult =
  | { readonly ok: true; readonly url: string; readonly meshRefs: readonly string[] }
  | { readonly ok: false; readonly reason: UrdfRejectReason; readonly detail: string };

const SCHEME = /^[a-z][a-z0-9+.-]*:\/\//i;
const PACKAGE_URI = /^package:\/\//i;

function extensionOf(reference: string): string {
  const withoutQuery = reference.split(/[?#]/, 1)[0];
  const lastDot = withoutQuery.lastIndexOf(".");
  return lastDot === -1 ? "" : withoutQuery.slice(lastDot + 1).toLowerCase();
}

function isAllowedMeshExtension(extension: string): boolean {
  return (MESH_EXTENSION_ALLOWLIST as readonly string[]).includes(extension);
}

// Validate a URDF URL and its mesh references. `meshRefs` are the mesh paths the
// URDF declares, as the backend rewrote them; the caller passes what it parsed.
export function validateUrdfSource(
  urdfUrl: string,
  meshRefs: readonly string[],
): UrdfSourceResult {
  if (SCHEME.test(urdfUrl)) {
    return { ok: false, reason: "external-origin", detail: urdfUrl };
  }
  for (const reference of meshRefs) {
    if (PACKAGE_URI.test(reference)) {
      return { ok: false, reason: "unrewritten-package-uri", detail: reference };
    }
    if (SCHEME.test(reference)) {
      return { ok: false, reason: "external-origin", detail: reference };
    }
    if (!isAllowedMeshExtension(extensionOf(reference))) {
      return { ok: false, reason: "mesh-extension-not-allowed", detail: reference };
    }
  }
  return { ok: true, url: urdfUrl, meshRefs };
}
