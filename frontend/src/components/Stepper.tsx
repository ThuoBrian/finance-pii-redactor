// File → Review → Download. Choosing the file and its settings is one stage
// (internal steps 0 and 1), so the tracker shows three. Moving between steps
// happens through each step's own buttons.

import { Icon } from "./Icon";

const STEPS = ["File", "Review", "Download"] as const;
export type StepIndex = 0 | 1 | 2 | 3;

export function Stepper({ current: step }: { current: StepIndex }) {
  const current = Math.max(0, step - 1);
  return (
    <nav aria-label="Progress">
      <ol className="flex items-center gap-2 text-sm">
        {STEPS.map((label, i) => {
          const state = i < current ? "done" : i === current ? "current" : "todo";
          return (
            <li key={label} className="flex items-center gap-2">
              {i > 0 && (
                <span aria-hidden className="h-0.5 w-6 overflow-hidden rounded-full bg-border-soft sm:w-12">
                  <span
                    className={`block h-full bg-primary transition-[width] duration-300 ${i <= current ? "w-full" : "w-0"}`}
                  />
                </span>
              )}
              <span
                aria-current={state === "current" ? "step" : undefined}
                className="flex items-center gap-2"
              >
                <span
                  aria-hidden
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
                    state === "todo"
                      ? "border border-border/70 bg-card text-muted"
                      : state === "current"
                        ? "bg-primary text-white shadow-sm ring-4 ring-primary/15"
                        : "bg-primary-soft text-primary"
                  }`}
                >
                  {state === "done" ? <Icon name="check" className="h-3.5 w-3.5" strokeWidth={3} /> : i + 1}
                </span>
                <span
                  className={`hidden sm:inline ${state === "current" ? "font-semibold text-text" : "text-muted"}`}
                >
                  {label}
                </span>
                <span className="sr-only">
                  {state === "done" ? " (done)" : state === "todo" ? " (not started)" : ""}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
