// Class-based bounded queues and priority-ordered draining — the mechanism behind
// CG-G-01b (a camera flood cannot delay lease/telemetry).

import { describe, expect, it } from "vitest";

import { BoundedQueue, PriorityDispatcher } from "./boundedQueue";
import { QUEUE_PROFILES } from "./envelope";

describe("BoundedQueue", () => {
  it("keeps only the latest under a latest_wins cap-1 queue and counts drops", () => {
    const queue = new BoundedQueue<number>(QUEUE_PROFILES.camera_preview);
    queue.enqueue(1);
    queue.enqueue(2);
    queue.enqueue(3);
    expect(queue.size).toBe(1);
    expect(queue.drainAll()).toEqual([3]);
    expect(queue.dropCount).toBe(2);
    expect(queue.dropRecord().classification).toBe("normal");
  });

  it("drops the oldest under a drop_oldest queue, keeping FIFO of the newest", () => {
    const queue = new BoundedQueue<number>(QUEUE_PROFILES.command);
    for (let value = 1; value <= 10; value += 1) {
      queue.enqueue(value);
    }
    expect(queue.size).toBe(QUEUE_PROFILES.command.boundedCapacity);
    expect(queue.drainAll()).toEqual([3, 4, 5, 6, 7, 8, 9, 10]);
    expect(queue.dropCount).toBe(2);
    expect(queue.dropRecord().classification).toBe("counted");
  });

  it("classifies a lease drop as a defect", () => {
    const queue = new BoundedQueue<number>(QUEUE_PROFILES.lease);
    queue.enqueue(1);
    queue.enqueue(2);
    expect(queue.dropRecord().classification).toBe("defect");
  });
});

describe("PriorityDispatcher", () => {
  it("drains lease before telemetry before camera regardless of arrival order", () => {
    const dispatcher = new PriorityDispatcher<string>(["lease", "telemetry", "camera_preview"]);
    // Arrive camera-heavy first, lease last.
    for (let index = 0; index < 100; index += 1) {
      dispatcher.enqueueFrame("camera", `cam${index}`);
    }
    dispatcher.enqueueFrame("telemetry", "tel");
    dispatcher.enqueueFrame("lease_grant", "lease");

    const order: string[] = [];
    dispatcher.drain((_queue, item) => order.push(item));

    expect(order[0]).toBe("lease");
    expect(order[1]).toBe("tel");
    // The camera queue is bounded at 1: the flood cannot build a backlog.
    expect(order.filter((item) => item.startsWith("cam"))).toHaveLength(1);
  });

  it("reports a frame class it does not hold as not enqueued", () => {
    const dispatcher = new PriorityDispatcher<string>(["lease", "telemetry", "camera_preview"]);
    // command is client_to_server; a receive dispatcher does not hold it.
    expect(dispatcher.enqueueFrame("command", "x")).toBe(false);
  });
});
