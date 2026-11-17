// File → Review → Download. Choosing the file and its settings is one stage
// (internal steps 0 and 1), so the tracker shows three. Moving between steps
// happens through each step's own buttons.

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
                <span
                  aria-hidden
                  className={`h-px w-6 sm:w-10 ${i <= current ? "bg-primary" : "bg-border-soft"}`}
                />
              )}
              <span
                aria-current={state === "current" ? "step" : undefined}
                className="flex items-center gap-2"
              >
                <span
                  aria-hidden
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${
                    state === "todo"
                      ? "border border-border text-muted"
                      : "bg-primary text-white"
                  }`}
                >
                  {state === "done" ? "✓" : i + 1}
                </span>
                <span
                  className={`hidden sm:inline ${state === "current" ? "font-semibold" : "text-muted"}`}
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
