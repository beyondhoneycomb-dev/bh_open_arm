// Diagnostic-bundle generator view (CG-G-S13c, CG-G-S13e). Renders the FR-OPS-023
// required-item checklist against what the backend's manifest can supply, blocks
// generation when any item is missing (no cherry-pick), and offers video/PII
// inclusion as opt-in toggles that default OFF.

import { useState } from "react";

import {
  REQUIRED_DIAGNOSTIC_ITEMS,
  bundleGenerationBlocked,
  defaultPrivacySelections,
  missingRequiredItems,
  type BundlePrivacySelections,
} from "./diagnosticBundle";
import type { BundleManifest } from "./types";

interface DiagnosticBundleViewProps {
  manifest: BundleManifest;
  onGenerate?: (selections: BundlePrivacySelections) => void;
}

export function DiagnosticBundleView({ manifest, onGenerate }: DiagnosticBundleViewProps) {
  const [privacy, setPrivacy] = useState<BundlePrivacySelections>(defaultPrivacySelections);
  const included = new Set(manifest.includedItemIds);
  const missing = missingRequiredItems(manifest);
  const blocked = bundleGenerationBlocked(manifest);

  return (
    <section
      className="oa-sys-view"
      aria-labelledby="oa-sys-bundle-title"
      data-testid="diagnostic-bundle"
      data-blocked={blocked}
    >
      <h2 id="oa-sys-bundle-title" className="oa-sys-view__title">
        진단 번들 — FR-OPS-023 전량
      </h2>

      <ul className="oa-sys-checklist" data-testid="bundle-checklist">
        {REQUIRED_DIAGNOSTIC_ITEMS.map((item) => {
          const present = included.has(item.id);
          return (
            <li
              key={item.id}
              data-testid={`bundle-item-${item.id}`}
              data-present={present}
            >
              <span aria-hidden="true">{present ? "✓" : "✗"}</span> {item.labelKo}
            </li>
          );
        })}
      </ul>

      {blocked && (
        <p className="oa-sys-alert" role="alert" data-testid="bundle-block">
          누락 항목이 있어 진단 번들 생성이 차단됩니다: {missing.join(", ")}
        </p>
      )}

      <fieldset className="oa-sys-privacy" data-testid="bundle-privacy">
        <legend>선택 포함 (기본 미포함)</legend>
        <label className="oa-sys-field oa-sys-field--check">
          <input
            type="checkbox"
            data-testid="bundle-include-video"
            checked={privacy.includeVideo}
            onChange={(event) =>
              setPrivacy((prev) => ({ ...prev, includeVideo: event.target.checked }))
            }
          />
          <span>영상 포함</span>
        </label>
        <label className="oa-sys-field oa-sys-field--check">
          <input
            type="checkbox"
            data-testid="bundle-include-pii"
            checked={privacy.includePii}
            onChange={(event) =>
              setPrivacy((prev) => ({ ...prev, includePii: event.target.checked }))
            }
          />
          <span>개인정보 포함</span>
        </label>
        {(privacy.includeVideo || privacy.includePii) && (
          <p className="oa-sys-warn" role="status" data-testid="bundle-privacy-warn">
            영상·개인정보가 번들에 포함됩니다.
          </p>
        )}
      </fieldset>

      <button
        type="button"
        className="oa-sys-generate"
        data-testid="bundle-generate"
        disabled={blocked}
        onClick={() => onGenerate?.(privacy)}
      >
        진단 번들 생성
      </button>
    </section>
  );
}
