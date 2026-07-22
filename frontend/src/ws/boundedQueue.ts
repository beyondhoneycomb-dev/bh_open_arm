// Class-based bounded queues and a priority dispatcher — the head-of-line
// mitigation the single WS rests on (CG-G-01b). Each frame class has its own
// bounded queue with the frozen CTR-PRIM@v1 capacity, drop policy and drop
// classification; the dispatcher drains classes strictly in priority order (lease
// first), so a camera flood can never delay a lease renewal or telemetry.

import {
  FRAME_TABLE,
  QUEUE_PROFILES,
  type DropClassification,
  type QueueName,
  type QueueProfile,
  type WsFrameType,
} from "./envelope";

export interface QueueDropCount {
  queue: QueueName;
  classification: DropClassification;
  count: number;
}

// One bounded queue class. When full it applies the profile's drop policy and
// counts the drop under the profile's classification, so the same shed frame
// reads the same way in every quality report.
export class BoundedQueue<T> {
  readonly profile: QueueProfile;
  private mItems: T[];
  private mDropCount: number;

  constructor(profile: QueueProfile) {
    this.profile = profile;
    this.mItems = [];
    this.mDropCount = 0;
  }

  get size(): number {
    return this.mItems.length;
  }

  get dropCount(): number {
    return this.mDropCount;
  }

  // Admit one item under the bounded-capacity rule. Returns whether it was kept.
  enqueue(item: T): boolean {
    if (this.mItems.length < this.profile.boundedCapacity) {
      this.mItems.push(item);
      return true;
    }
    if (this.profile.dropPolicy === "block") {
      // No room and no eviction: the newest is refused, and the refusal is counted.
      this.mDropCount += 1;
      return false;
    }
    // Both latest_wins and drop_oldest admit the newest by evicting the oldest.
    this.mItems.shift();
    this.mItems.push(item);
    this.mDropCount += 1;
    return true;
  }

  // Remove and return every queued item in FIFO order.
  drainAll(): T[] {
    const drained = this.mItems;
    this.mItems = [];
    return drained;
  }

  dropRecord(): QueueDropCount {
    return {
      queue: this.profile.name,
      classification: this.profile.dropClassification,
      count: this.mDropCount,
    };
  }
}

// Routes frames to their bound queue class and drains strictly by priority. The
// class set is explicit so a receive-side dispatcher can hold only the classes it
// actually receives (lease, telemetry, camera).
export class PriorityDispatcher<T> {
  private mQueues: Map<QueueName, BoundedQueue<T>>;
  private mDrainOrder: QueueName[];

  constructor(queues: QueueName[]) {
    this.mQueues = new Map();
    for (const name of queues) {
      this.mQueues.set(name, new BoundedQueue<T>(QUEUE_PROFILES[name]));
    }
    // Ascending priority value is served first; the lease class (0) leads.
    this.mDrainOrder = [...queues].sort(
      (left, right) => QUEUE_PROFILES[left].priority - QUEUE_PROFILES[right].priority,
    );
  }

  queueFor(frameType: WsFrameType): QueueName {
    return FRAME_TABLE[frameType].queue;
  }

  // Enqueue by frame type. Returns false when the frame's class is not held by
  // this dispatcher (an outbound-only class handed to a receive dispatcher).
  enqueueFrame(frameType: WsFrameType, item: T): boolean {
    const queue = this.mQueues.get(this.queueFor(frameType));
    if (!queue) {
      return false;
    }
    return queue.enqueue(item);
  }

  // Drain every class in priority order, delivering each item to the handler. A
  // higher-priority class is fully drained before a lower-priority one begins.
  drain(handler: (queue: QueueName, item: T) => void): void {
    for (const name of this.mDrainOrder) {
      const queue = this.mQueues.get(name);
      if (!queue) {
        continue;
      }
      for (const item of queue.drainAll()) {
        handler(name, item);
      }
    }
  }

  dropCounts(): QueueDropCount[] {
    return this.mDrainOrder.map((name) => this.mQueues.get(name)!.dropRecord());
  }
}
