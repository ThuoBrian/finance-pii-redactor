// Polls the job while its background task runs and reports the outcome.
// Shows how far it has got, a rough time left once the pace is known, and
// a Cancel button: the scan stops at its next step and any earlier result
// stays as it was.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api, plural } from "../api";
import { Button } from "./ui";

/** "about 3 minutes left", or null while the estimate would be noise. */
export function timeLeft(
  done: number,
  total: number,
  elapsedMs: number,
  doneAtStart = 0,
): string | null {
  const progressed = done - doneAtStart;
  if (total <= 0 || progressed <= 0 || done / total < 0.05) return null;
  const remainingMs = (elapsedMs / progressed) * (total - done);
  // A quick run needs no estimate.
  if (elapsedMs + remainingMs < 20_000) return null;
  const minutes = Math.round(remainingMs / 60_000);
  if (minutes < 1) return "less than a minute left";
  return `about ${plural(minutes, "minute")} left`;
}

export function TaskProgress({
  jobId,
  onDone,
  onError,
  onCancelled,
  unit,
}: {
  jobId: string;
  /** What the progress counts, singular, e.g. "unique value" or "page". */
  unit: string;
  onDone: () => void;
  onError: (message: string) => void;
  onCancelled: () => void;
}) {
  const status = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.jobStatus(jobId),
    refetchInterval: (query) =>
      query.state.data?.task.status === "running" ? 500 : false,
    gcTime: 0,
  });
  const cancel = useMutation({ mutationFn: () => api.cancelJob(jobId) });
  const task = status.data?.task;
  // When progress was first seen, for the time estimate.
  const started = useRef<{ at: number; done: number } | null>(null);
  if (task && task.total && started.current === null) {
    started.current = { at: Date.now(), done: task.done };
  }

  useEffect(() => {
    if (task?.status === "done") onDone();
    else if (task?.status === "cancelled") onCancelled();
    else if (task?.status === "error") onError(task.error);
    else if (status.error) onError(status.error.message);
  }, [task?.status, task?.error, status.error, onDone, onError, onCancelled]);

  const pct = task && task.total ? Math.round((task.done / task.total) * 100) : null;
  const estimate =
    task && started.current
      ? timeLeft(task.done, task.total, Date.now() - started.current.at, started.current.done)
      : null;
  const cancelling = cancel.isPending || cancel.data?.cancelling;

  return (
    <div className="card p-6" aria-live="polite">
      <div className="flex items-start justify-between gap-3">
        <p className="flex items-center gap-2.5 font-medium">
          {task?.status === "running" && !cancelling && (
            <span aria-hidden className="relative flex h-2.5 w-2.5">
              <span className="absolute inset-0 animate-ping rounded-full bg-primary opacity-40" />
              <span className="relative h-2.5 w-2.5 rounded-full bg-primary" />
            </span>
          )}
          {cancelling ? "Cancelling..." : task?.label || "Starting..."}
        </p>
        <Button
          size="sm"
          disabled={Boolean(cancelling) || task?.status !== "running"}
          onClick={() => cancel.mutate()}
        >
          Cancel
        </Button>
      </div>
      <div
        className="mt-4 h-2.5 overflow-hidden rounded-full bg-surface-2"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label="Progress"
      >
        <div
          className={`h-full rounded-full bg-primary transition-[width] duration-500 ${task?.status === "running" ? "progress-stripes" : ""} ${pct === null ? "w-1/3 animate-pulse" : ""}`}
          style={pct === null ? undefined : { width: `${pct}%` }}
        />
      </div>
      <p className="mt-3 text-sm text-muted">
        {task && task.total
          ? `${task.done.toLocaleString()} of ${plural(task.total, unit)} checked${estimate ? ` · ${estimate}` : ""}`
          : "This can take a while for a big file. Keep this page open."}
      </p>
    </div>
  );
}

/** The whole "Redacting" screen shown while a scan runs. */
export function ScanProgress({
  jobId,
  unit,
  progress,
}: {
  jobId: string;
  unit: string;
  progress: { onDone: () => void; onError: (message: string) => void; onCancelled: () => void };
}) {
  return (
    <section className="mx-auto max-w-2xl">
      <h1 tabIndex={-1} className="mb-6 text-3xl font-semibold tracking-tight">
        Redacting
      </h1>
      <TaskProgress jobId={jobId} unit={unit} {...progress} />
    </section>
  );
}
