// Public surface of the mode / control-authority display module (WP-G-04). Screen
// WPs import components and logic from here; the mode-transition semantics (send
// action authority moves, the link never re-opens) live in the modules re-exported
// below.

export * from "./modes";
export * from "./roles";
export * from "./lease";
export * from "./handoff";
export * from "./takeover";
export * from "./health";
export { ModeBadge, type ModeBadgeProps } from "./ModeBadge";
export { ModeAuthorityTable, type ModeAuthorityTableProps } from "./ModeAuthorityTable";
export { HandoffProgress, type HandoffProgressProps } from "./HandoffProgress";
export { ForceTakeoverDialog, type ForceTakeoverDialogProps } from "./ForceTakeoverDialog";
export { ControlLeaseView, type ControlLeaseViewProps } from "./ControlLeaseView";
