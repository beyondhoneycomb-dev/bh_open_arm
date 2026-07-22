// The task prompt panel. The `single_task` string the backend attaches to every
// recorded frame (TASK_KEY) is shown to the operator during a session, and can be
// edited between sessions. Editing SENDS a set_task intent; the backend owns the
// prompt attached to frames — the screen keeps only the draft text of the input.

import { useState } from "react";

import type { TaskPrompt } from "./types";

export interface TaskPromptViewProps {
  prompt: TaskPrompt;
  editable: boolean;
  onChange: (task: string) => void;
}

export function TaskPromptView({ prompt, editable, onChange }: TaskPromptViewProps) {
  const [draft, setDraft] = useState(prompt.text);

  return (
    <section className="oa-collect__task" aria-labelledby="oa-collect-task-title">
      <h2 id="oa-collect-task-title" className="oa-collect__section-title">
        태스크 프롬프트
      </h2>
      {editable ? (
        <div className="oa-collect__task-edit">
          <label className="oa-collect__task-label" htmlFor="oa-collect-task-input">
            프레임에 부착될 태스크
          </label>
          <input
            id="oa-collect-task-input"
            className="oa-collect__task-input"
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button
            type="button"
            className="oa-collect__task-apply"
            disabled={draft.trim().length === 0 || draft === prompt.text}
            onClick={() => onChange(draft)}
          >
            태스크 적용
          </button>
        </div>
      ) : (
        <p className="oa-collect__task-active" role="status" data-testid="task-prompt">
          {prompt.text}
        </p>
      )}
    </section>
  );
}
