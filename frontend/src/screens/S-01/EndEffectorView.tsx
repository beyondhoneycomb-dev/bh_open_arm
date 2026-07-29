// The per-arm end-effector control (render half). It lists the tools the BACKEND
// registry sent, marks the one the stored config names, and reports a choice
// upward — it holds no tool list of its own and writes nothing itself.
//
// Three states refuse instead of showing a plausible answer, because every one of
// them decides whether CAN id 0x08 is addressed on that arm:
//   - the registry could not be read  -> no choices are offered at all
//   - the config could not be read    -> no arm shows a fitted tool
//   - the stored id is not registered -> that arm shows no selection and says why
// The selection always mirrors the stored config, never the click: after a failed
// write the operator must see what the backend actually holds.
//
// Mass is shown as a fact and gates nothing — it cannot be measured with torque
// off, so "unmeasured" is a normal state to work in, not an error to clear.

import type { ToolChoice } from "../../config/endEffectorTools";
import { ARM_SIDES, type ArmSide, type EndEffectorConfig } from "../../config/schema";
import {
  ARM_SIDE_LABELS,
  DEFAULT_TOOL_NOTICE,
  GRIPPER_ABSENT_CONSEQUENCE,
  GRIPPER_POLLED_CONSEQUENCE,
  MASS_UNMEASURED_DETAIL,
  PANEL_TITLE,
  TOOL_CHANGE_MASS_NOTICE,
  massFactText,
  unknownToolText,
} from "./endEffector";

interface EndEffectorViewProps {
  // The stored per-arm build, or null when the config could not be read.
  endEffector: EndEffectorConfig | null;
  tools: readonly ToolChoice[];
  // Why no choices can be offered, when the registry could not be read.
  toolsNotice: string | null;
  // Why no fitted tool can be shown, when the config could not be read.
  configNotice: string | null;
  // Set when the last write was refused; the selection below is still the stored one.
  saveNotice: string | null;
  onSelectTool: (side: ArmSide, toolId: string) => void;
}

export function EndEffectorView({
  endEffector,
  tools,
  toolsNotice,
  configNotice,
  saveNotice,
  onSelectTool,
}: EndEffectorViewProps) {
  return (
    <section
      className="oa-dash__panel"
      aria-labelledby="oa-dash-ee-title"
      data-panel="end-effector"
      data-testid="end-effector-panel"
    >
      <h2 id="oa-dash-ee-title" className="oa-dash__panel-title">
        {PANEL_TITLE}
      </h2>

      <p className="oa-dash__tile-sub">{DEFAULT_TOOL_NOTICE}</p>

      {saveNotice === null ? null : (
        <p className="oa-dash__tile-warn" role="alert" data-testid="ee-save-notice">
          {saveNotice}
        </p>
      )}

      {toolsNotice === null ? null : (
        <p className="oa-dash__tile-warn" role="alert" data-testid="ee-tools-notice">
          {toolsNotice}
        </p>
      )}

      {configNotice === null ? null : (
        <p className="oa-dash__tile-sub" role="status" data-testid="ee-config-notice">
          {configNotice}
        </p>
      )}

      {endEffector === null || toolsNotice !== null
        ? null
        : ARM_SIDES.map((side) => {
            const arm = endEffector[side];
            const fitted = tools.find((tool) => tool.toolId === arm.toolId) ?? null;
            return (
              <fieldset
                key={side}
                className="oa-dash__ee-arm"
                data-testid={`ee-arm-${side}`}
                data-tool-id={arm.toolId}
              >
                <legend className="oa-dash__ee-arm-label">{ARM_SIDE_LABELS[side]}</legend>

                {fitted === null ? (
                  <p className="oa-dash__tile-warn" role="alert" data-testid={`ee-unknown-${side}`}>
                    {unknownToolText(arm.toolId)}
                  </p>
                ) : null}

                <p
                  className="oa-dash__ee-mass"
                  data-testid={`ee-mass-${side}`}
                  data-mass-measured={arm.toolMassKg !== null}
                >
                  {massFactText(arm.toolMassKg)}
                  {arm.toolMassKg === null ? (
                    <span className="oa-dash__tile-sub"> {MASS_UNMEASURED_DETAIL}</span>
                  ) : null}
                </p>

                {tools.map((tool) => (
                  <label
                    key={tool.toolId}
                    className="oa-dash__ee-choice"
                    data-ee-choice={`${side}:${tool.toolId}`}
                    data-gripper-motor={tool.gripperMotor}
                  >
                    <input
                      type="radio"
                      name={`oa-dash-ee-${side}`}
                      value={tool.toolId}
                      checked={tool.toolId === arm.toolId}
                      onChange={() => onSelectTool(side, tool.toolId)}
                    />
                    <span className="oa-dash__ee-tool">
                      <span className="oa-dash__ee-tool-label">{tool.label}</span>
                      <span className="oa-dash__ee-consequence">
                        {tool.gripperMotor
                          ? GRIPPER_POLLED_CONSEQUENCE
                          : GRIPPER_ABSENT_CONSEQUENCE}
                      </span>
                    </span>
                  </label>
                ))}

                <p className="oa-dash__tile-sub">{TOOL_CHANGE_MASS_NOTICE}</p>
              </fieldset>
            );
          })}
    </section>
  );
}
