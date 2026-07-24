// The chart-key contract (CG-G-S10b / FR-GUI-124). The training screen may chart ONLY
// the metrics `MetricsTracker` actually emits — inventing a key ("val_loss curve",
// "accuracy") would draw a line the trainer never produces, which reads as data and is
// a lie. The set below is exactly the seven keys the installed lerobot 0.6.0
// `lerobot/scripts/lerobot_train.py` registers on its train MetricsTracker:
//   loss, grad_norm, lr, update_s, dataloading_s, samples_per_s   (always)
//   gpu_mem_gb                                                    (added under CUDA)
// `gpu_mem_gb` is the ONLY GPU figure MetricsTracker emits; utilisation/temperature are
// a separate NVML reading (see types.ts GpuReading, FR-GUI-126), never charted from a
// fabricated MetricsTracker key.

export const METRIC_KEYS = [
  "loss",
  "grad_norm",
  "lr",
  "samples_per_s",
  "update_s",
  "dataloading_s",
  "gpu_mem_gb",
] as const;

export type MetricKey = (typeof METRIC_KEYS)[number];

const METRIC_KEY_SET: ReadonlySet<string> = new Set(METRIC_KEYS);

// Whether a proposed chart key is one MetricsTracker actually emits. The chart code
// routes every series through this, so a key that is not in the set cannot be plotted.
export function isMetricKey(key: string): key is MetricKey {
  return METRIC_KEY_SET.has(key);
}

// A human label + unit for a metric key, for axis and legend text. Labels describe the
// existing key; they add no new series.
export interface MetricMeta {
  key: MetricKey;
  label: string;
  unit: string;
}

const METRIC_META: Readonly<Record<MetricKey, MetricMeta>> = {
  loss: { key: "loss", label: "손실 (loss)", unit: "" },
  grad_norm: { key: "grad_norm", label: "그래디언트 노름 (grad_norm)", unit: "" },
  lr: { key: "lr", label: "학습률 (lr)", unit: "" },
  samples_per_s: { key: "samples_per_s", label: "처리량 (samples_per_s)", unit: "smp/s" },
  update_s: { key: "update_s", label: "업데이트 시간 (update_s)", unit: "s" },
  dataloading_s: { key: "dataloading_s", label: "데이터로딩 시간 (dataloading_s)", unit: "s" },
  gpu_mem_gb: { key: "gpu_mem_gb", label: "GPU 메모리 (gpu_mem_gb)", unit: "GB" },
};

export function metricMeta(key: MetricKey): MetricMeta {
  return METRIC_META[key];
}
