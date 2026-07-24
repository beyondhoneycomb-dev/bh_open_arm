// CG-4A-G1b unit coverage: the metric key set is exactly MetricsTracker's seven outputs
// and the guard rejects anything else.

import { describe, expect, it } from "vitest";

import { METRIC_KEYS, isMetricKey, metricMeta } from "./metrics";

describe("metrics key contract (CG-4A-G1b)", () => {
  it("is exactly the seven MetricsTracker outputs", () => {
    expect([...METRIC_KEYS].sort()).toEqual(
      ["dataloading_s", "gpu_mem_gb", "grad_norm", "loss", "lr", "samples_per_s", "update_s"].sort(),
    );
  });

  it("accepts each real key and rejects an invented one", () => {
    for (const key of METRIC_KEYS) {
      expect(isMetricKey(key)).toBe(true);
    }
    expect(isMetricKey("val_loss")).toBe(false);
    expect(isMetricKey("accuracy")).toBe(false);
    expect(isMetricKey("success_rate")).toBe(false);
  });

  it("has a meta label+unit for every key and no others", () => {
    for (const key of METRIC_KEYS) {
      expect(metricMeta(key).key).toBe(key);
    }
  });
});
