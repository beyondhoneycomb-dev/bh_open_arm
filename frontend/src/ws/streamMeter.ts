// The rolling FPS / jitter_ms / drop meter. It instruments a set of channels
// DERIVED at runtime from `robot.observation_features` (and the active camera
// preview slots) — never a hardcoded count or channel name (CG-G-01e). Each
// channel keeps a rolling window of arrival instants; FPS and inter-arrival
// jitter are computed from that window, and drops are counted separately.

const DEFAULT_METER_WINDOW_MS = 1000;
const MS_PER_SECOND = 1000;

export interface StreamStats {
  channel: string;
  fps: number;
  jitterMs: number;
  dropCount: number;
  sampleCount: number;
}

interface ChannelState {
  stamps: number[];
  drops: number;
}

// The instrumented target set. Telemetry targets are the observation feature keys
// exactly as the backend reports them; camera targets are the active preview
// slots. Both are inputs, so the instrument count follows the live configuration
// rather than a compiled-in constant.
export function instrumentedChannels(
  observationFeatures: readonly string[],
  cameraSlots: readonly string[] = [],
): string[] {
  return [...observationFeatures, ...cameraSlots];
}

export class StreamMeter {
  private mWindowMs: number;
  private mChannels: Map<string, ChannelState>;

  constructor(channels: readonly string[], windowMs: number = DEFAULT_METER_WINDOW_MS) {
    this.mWindowMs = windowMs;
    this.mChannels = new Map();
    for (const channel of channels) {
      this.mChannels.set(channel, { stamps: [], drops: 0 });
    }
  }

  // The number of instrumented targets — equal to the size of the derived set,
  // which is the property CG-G-01e asserts.
  get instrumentedCount(): number {
    return this.mChannels.size;
  }

  channels(): string[] {
    return [...this.mChannels.keys()];
  }

  private stateFor(channel: string): ChannelState {
    let state = this.mChannels.get(channel);
    if (!state) {
      state = { stamps: [], drops: 0 };
      this.mChannels.set(channel, state);
    }
    return state;
  }

  private prune(state: ChannelState, nowMs: number): void {
    const cutoff = nowMs - this.mWindowMs;
    while (state.stamps.length > 0 && state.stamps[0] < cutoff) {
      state.stamps.shift();
    }
  }

  // Record one delivered frame on a channel at the given client-clock instant.
  mark(channel: string, nowMs: number): void {
    const state = this.stateFor(channel);
    state.stamps.push(nowMs);
    this.prune(state, nowMs);
  }

  // Record one dropped frame on a channel (a queue eviction or a backpressure shed).
  markDrop(channel: string): void {
    this.stateFor(channel).drops += 1;
  }

  stats(channel: string): StreamStats {
    const state = this.stateFor(channel);
    return {
      channel,
      fps: (state.stamps.length * MS_PER_SECOND) / this.mWindowMs,
      jitterMs: standardDeviation(intervals(state.stamps)),
      dropCount: state.drops,
      sampleCount: state.stamps.length,
    };
  }

  allStats(): StreamStats[] {
    return this.channels().map((channel) => this.stats(channel));
  }
}

function intervals(stamps: readonly number[]): number[] {
  const out: number[] = [];
  for (let index = 1; index < stamps.length; index += 1) {
    out.push(stamps[index] - stamps[index - 1]);
  }
  return out;
}

function standardDeviation(values: readonly number[]): number {
  if (values.length < 2) {
    return 0;
  }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance =
    values.reduce((sum, value) => sum + (value - mean) * (value - mean), 0) / values.length;
  return Math.sqrt(variance);
}
