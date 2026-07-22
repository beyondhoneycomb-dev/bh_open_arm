// Test harness for the manual-motion lane: a recording command sink and a source
// override helper, so the CG-G-S04* tests drive the screen against the offline
// fixture with no socket. Not production wiring — only the *.test.tsx files import
// it — but it deliberately contains no clamp/limit/convert logic either, so the
// CG-G-S04a static scan holds even here.

import type { ManualCommand, ManualCommandSink } from "./commands";
import { defaultManualSource, type ManualSource } from "./manualSource";

export class RecordingSink implements ManualCommandSink {
  readonly sent: ManualCommand[];

  constructor() {
    this.sent = [];
  }

  send(command: ManualCommand): void {
    this.sent.push(command);
  }

  ops(): string[] {
    return this.sent.map((command) => command.op);
  }
}

export function sourceWith(overrides: Partial<ManualSource>): ManualSource {
  return { ...defaultManualSource(), ...overrides };
}
