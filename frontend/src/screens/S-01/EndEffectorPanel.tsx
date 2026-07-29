// The end-effector control's wiring: it reads the registered tools from the
// backend registry, reads the fitted build from the shared runtime config, and
// writes a chosen tool back through the config context's save (PUT of the one
// subobject). The rendering is EndEffectorView's.
//
// The shown selection is the stored config and never the click. A refused write
// leaves the control showing what the backend actually holds and says the write
// failed — an optimistic selection would tell the operator a gripper is fitted
// while the backend still polls seven ids, or the reverse.
//
// Changing the tool clears the mass to unmeasured. The measurement belonged to
// the tool that was on the arm; carrying it over would hand gravity compensation
// a number for hardware that is no longer there. Re-picking the tool already
// fitted is a no-op for the same reason: it must not discard a real measurement.

import { useCallback, useEffect, useState } from "react";

import type { ConfigStatus } from "../../app/ConfigContext";
import { useConfig } from "../../app/ConfigContext";
import type { FetchLike } from "../../config/client";
import { fetchToolChoices, type ToolChoice } from "../../config/endEffectorTools";
import type { ArmSide, ConfigSubobjectKey, EndEffectorConfig } from "../../config/schema";
import { EndEffectorView } from "./EndEffectorView";
import {
  CONFIG_DEFAULTED_TEXT,
  CONFIG_LOADING_TEXT,
  CONFIG_UNREADABLE_TEXT,
  SAVE_FAILED_TEXT,
  TOOLS_LOADING_TEXT,
  TOOLS_UNREADABLE_TEXT,
} from "./endEffector";

// The one runtime_config subobject this panel owns; every other subobject is
// untouched by its writes.
const END_EFFECTOR_KEY = "endEffector" as const;

interface EndEffectorPanelProps {
  // Injectable for tests, as ConfigProvider takes its own; the browser passes
  // nothing and the global fetch is used.
  fetchImpl?: FetchLike;
}

function resolveConfigNotice(
  status: ConfigStatus,
  defaulted: readonly ConfigSubobjectKey[],
): string | null {
  if (status === "loading") {
    return CONFIG_LOADING_TEXT;
  }
  if (status === "error") {
    return CONFIG_UNREADABLE_TEXT;
  }
  if (defaulted.includes(END_EFFECTOR_KEY)) {
    return CONFIG_DEFAULTED_TEXT;
  }
  return null;
}

export function EndEffectorPanel({ fetchImpl }: EndEffectorPanelProps) {
  const { config, status, defaulted, save } = useConfig();
  const [tools, setTools] = useState<readonly ToolChoice[]>([]);
  const [toolsNotice, setToolsNotice] = useState<string | null>(TOOLS_LOADING_TEXT);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTools(): Promise<void> {
      try {
        const choices = await fetchToolChoices(fetchImpl ?? fetch);
        if (!cancelled) {
          setTools(choices);
          setToolsNotice(null);
        }
      } catch {
        // A list that could not be read whole offers no choices at all: a
        // shorter list would read as the complete one.
        if (!cancelled) {
          setTools([]);
          setToolsNotice(TOOLS_UNREADABLE_TEXT);
        }
      }
    }

    void loadTools();
    return () => {
      cancelled = true;
    };
  }, [fetchImpl]);

  const handleSelectTool = useCallback(
    async (side: ArmSide, toolId: string): Promise<void> => {
      const current = config[END_EFFECTOR_KEY];
      if (current[side].toolId === toolId) {
        return;
      }
      const next: EndEffectorConfig = { ...current };
      next[side] = { toolId, toolMassKg: null };
      try {
        await save(END_EFFECTOR_KEY, next);
        setSaveNotice(null);
      } catch {
        setSaveNotice(SAVE_FAILED_TEXT);
      }
    },
    [config, save],
  );

  return (
    <EndEffectorView
      endEffector={status === "ready" ? config[END_EFFECTOR_KEY] : null}
      tools={tools}
      toolsNotice={toolsNotice}
      configNotice={resolveConfigNotice(status, defaulted)}
      saveNotice={saveNotice}
      onSelectTool={handleSelectTool}
    />
  );
}
