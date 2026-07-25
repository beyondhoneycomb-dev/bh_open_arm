// Public surface of the WP-5-04 GUI completion audit (frontend/src/audit/**,
// EXCLUSIVE). The audit is importable, pure logic over the committed 13-screen tree;
// it builds and edits no screen. The *.test.ts files supply the file corpus (via
// testSupport) and the scan patterns that carry forbidden tokens, then run these
// functions across the four §2.6 audit axes / six acceptance gates (CG-5-04a..f).

export type { AuditViolation, ScannedSource, NamedPattern } from "./types";

export {
  stripComments,
  scanForPatterns,
  findDisallowedUrls,
  findOffOriginTags,
  DEFAULT_ALLOWED_HOSTS,
} from "./scan";

export {
  SCREEN_INVENTORY,
  VIEWPORT_ROUTE,
  inventoryRow,
  canonScreenIds,
  canonScreenPaths,
  type ScreenInventoryRow,
  type ViewportTier,
} from "./screenInventory";

export {
  auditRouteInventory,
  auditScreenDirectories,
  type RegistryScreen,
} from "./routeInventoryAudit";

export {
  detectViewportEmbed,
  auditViewportPermission,
  type EmbedObservation,
} from "./viewportPermissionAudit";

export {
  modeAuthoritiesFromCatalog,
  auditCommandSourceExclusivity,
  teleopExpressesExclusivity,
  type ModeAuthority,
  type CatalogMode,
} from "./commandSourceAudit";
