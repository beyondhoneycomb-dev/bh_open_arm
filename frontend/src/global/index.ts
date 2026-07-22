// Public surface of the always-on safety elements (WP-G-03). The shell (WP-G-00)
// mounts GlobalSafetyBar; screens (WP-G-S01..S13) consume the badges, the
// preflight gate, the notification center, and the shortcut registry. Everything
// re-exported here is the boundary other WPs depend on.

export { GlobalSafetyBar, type GlobalSafetyBarProps } from "./GlobalSafetyBar";
export { StatusBadgeBar, type RobotBadgeState, type StatusBadgeBarProps } from "./StatusBadgeBar";
export { StopControls, type StopControlsProps } from "./StopControls";
export {
  SOFT_STOP,
  HARD_ESTOP,
  HARD_ESTOP_DROP_WARNING,
  STOP_KINDS,
  type StopKind,
} from "./stopControls";
export { CanBadge } from "./CanBadge";
export {
  deriveCanState,
  hasIntruder,
  isControlBlocked,
  canStartupBlockers,
  BOUND_SOCKET_SOLE_OWNER,
  CAN_FD_NOMINAL_BITRATE,
  CAN_FD_DATA_BITRATE,
  type CanInterfaceStatus,
  type CanState,
  type CanLinkState,
} from "./canStatus";
export { VelocityTorqueBadge } from "./VelocityTorqueBadge";
export { PushToHubBadge, PushToHubConfirm } from "./PushToHubBadge";
export {
  velocityTorqueIsWarning,
  setVelocityTorqueCoupled,
  pushToHubRequiresConfirm,
  VELOCITY_TORQUE_OFF_WARNING,
  PUSH_TO_HUB_UPLOAD_WARNING,
  type VelocityTorqueState,
  type PushToHubState,
} from "./flags";
export { PreflightBanner } from "./PreflightBanner";
export {
  PREFLIGHT_ITEM_IDS,
  PREFLIGHT_ITEM_LABELS,
  DISK_MIN_HEADROOM_HOURS,
  canStartSession,
  failedPreflightItems,
  preflightIsComplete,
  type PreflightItem,
  type PreflightItemId,
} from "./preflight";
export { NotificationCenter, NotificationBadge } from "./NotificationCenter";
export {
  badgeIsHeld,
  heldCount,
  heldNotifications,
  acknowledge,
  type Notification,
} from "./notifications";
export { DummyModeBanner } from "./DummyModeBanner";
export {
  DEFAULT_SHORTCUTS,
  SHORTCUT_ACTIONS,
  getBinding,
  rebind,
  conflictingActions,
  type ShortcutAction,
  type ShortcutBinding,
} from "./shortcuts";
export {
  LIVE_LINK_MODES,
  estopMatrix,
  ESTOP_MATRIX_SIZE,
  type LiveLinkMode,
  type SafetyContext,
} from "./modes";
export {
  Severity,
  SEVERITY_NAMES,
  holdsBadgeUntilAck,
  isValidErrorCode,
  OA_DOMAINS,
  type SeverityValue,
  type SeverityName,
} from "./contracts/errorCodes";
export { CONTROL_ROLES, type ControlRole } from "./contracts/wsRoles";
