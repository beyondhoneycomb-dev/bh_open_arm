// The task switcher (RolloutConfig.task, 11 §2.7). It selects which language instruction is
// active for the rollout. The screen sends the intent and renders the backend's active
// task; it fabricates no task. Disabled on a schema lock.

import type { InferenceTask } from "./types";

export interface TaskSwitcherViewProps {
  tasks: readonly InferenceTask[];
  activeTaskId: string;
  disabled: boolean;
  onSelectTask: (taskId: string) => void;
}

export function TaskSwitcherView({ tasks, activeTaskId, disabled, onSelectTask }: TaskSwitcherViewProps) {
  return (
    <section
      className="oa-inf__tasks"
      aria-labelledby="oa-inf-tasks-title"
      data-testid="task-switcher"
      data-disabled={disabled}
    >
      <h2 id="oa-inf-tasks-title" className="oa-inf__section-title">
        태스크
      </h2>
      <ul className="oa-inf__task-list">
        {tasks.map((task) => {
          const selected = task.id === activeTaskId;
          return (
            <li key={task.id}>
              <button
                type="button"
                className="oa-inf__task-row"
                aria-pressed={selected}
                data-selected={selected}
                data-testid={`task-option-${task.id}`}
                disabled={disabled}
                onClick={() => onSelectTask(task.id)}
              >
                <span className="oa-inf__task-id">{task.id}</span>
                <span className="oa-inf__task-prompt">{task.prompt}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
