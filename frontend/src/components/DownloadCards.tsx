// The Download step: its frame, the two cards and the buttons in them.
// Sorting files by who may see them is the point of this step: the card a
// file sits in is its classification.
import { useMutation, type UseQueryResult } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { downloadFile, plural } from "../api";
import { Button, Notice, Spinner } from "./ui";

export type ExpectedFile = { kind: string; label: string };

/**
 * Track which expected files were downloaded for the current build.
 *
 * ``version`` changes on every rebuild: a file downloaded before an Apply is
 * out of date, so it counts as missing again. ``onPending`` hears the labels
 * still missing (and an empty list when the flow goes away), so the app can
 * warn before work is lost.
 */
export function useDownloadTracker(
  version: number,
  expected: ExpectedFile[],
  onPending: (missing: string[]) => void,
) {
  const [done, setDone] = useState<ReadonlySet<string>>(new Set());
  useEffect(() => setDone(new Set()), [version]);
  const missing = useMemo(
    () => expected.filter((e) => !done.has(e.kind)).map((e) => e.label),
    [expected, done],
  );
  const signature = missing.join("|");
  useEffect(() => {
    onPending(missing);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- report on change only
  }, [signature]);
  useEffect(() => () => onPending([]), []); // eslint-disable-line react-hooks/exhaustive-deps
  const markDone = useCallback((kind: string) => setDone((d) => new Set(d).add(kind)), []);
  return { isDone: (kind: string) => done.has(kind), markDone };
}

export type DownloadTracker = ReturnType<typeof useDownloadTracker>;

/** The warning beside every names-bearing mapping download (Confidential). */
export function crosswalkWarning(replacement: "codes" | "labels", file: string): string {
  return (
    `Lists real names next to their ${replacement}, so it can re-identify ` +
    `everyone in the file. Store it somewhere secure, apart from the ${file}, ` +
    "and never send the two together."
  );
}

export function ExclusionWarning({ excluded }: { excluded: string[] }) {
  if (!excluded.length) return null;
  return (
    <Notice tone="warn">
      <strong>{plural(excluded.length, "term")} will not be hidden</strong>, at your
      request: {excluded.join(", ")}. They appear in the downloaded file exactly as
      in the original. Go back to Review, tick them and apply if that is not what
      you meant.
    </Notice>
  );
}

export function DownloadButton({
  jobId,
  kind,
  label,
  tracker,
  variant = "primary",
}: {
  jobId: string;
  kind: string;
  label: string;
  /** Marks the file downloaded for the current build. */
  tracker: DownloadTracker;
  variant?: "primary" | "secondary";
}) {
  const done = tracker.isDone(kind);
  const download = useMutation({
    mutationFn: () => downloadFile(jobId, kind),
    onSuccess: () => tracker.markDone(kind),
  });
  return (
    <div>
      <Button
        variant={done ? "secondary" : variant}
        className="w-full"
        disabled={download.isPending}
        onClick={() => download.mutate()}
      >
        {download.isPending ? "Preparing..." : label}
      </Button>
      {done && !download.isPending && (
        <p className="mt-1 text-xs text-success" role="status">
          ✓ Downloaded. You can download it again if you need another copy.
        </p>
      )}
      {download.error && (
        <Notice tone="danger" className="mt-2">
          {download.error.message}
        </Notice>
      )}
    </div>
  );
}

/** The Excel/Word name mapping (real names, Confidential), or why there is none. */
export function CrosswalkCard({
  jobId,
  hasMapping,
  tracker,
}: {
  jobId: string;
  hasMapping: boolean;
  tracker: DownloadTracker;
}) {
  if (!hasMapping) {
    return <p className="text-muted">No names were replaced, so there is no mapping file.</p>;
  }
  return (
    <>
      <DownloadButton
        jobId={jobId}
        kind="crosswalk"
        label="Download name mapping (CSV)"
        tracker={tracker}
        variant="secondary"
      />
      <p className="text-muted">{crosswalkWarning("codes", "redacted file")}</p>
    </>
  );
}

/**
 * The Download step's frame: heading, loading and error states, the
 * terms-left-visible warning, and the Back / Redact another file footer.
 * ``children`` renders the format's own notes and cards once data is in.
 */
export function DownloadStep<T extends { excluded: string[] }>({
  info,
  onBack,
  onFinish,
  children,
}: {
  info: UseQueryResult<T>;
  onBack: () => void;
  onFinish: () => void;
  children: (data: T) => ReactNode;
}) {
  const d = info.data;
  return (
    <section aria-labelledby="download-heading" className="mx-auto max-w-4xl space-y-4">
      <h1 tabIndex={-1} id="download-heading" className="text-2xl font-semibold tracking-tight">
        Download
      </h1>
      {info.error && <Notice tone="danger">{info.error.message}</Notice>}
      {!d ? (
        <Spinner label="Loading..." />
      ) : (
        <>
          <ExclusionWarning excluded={d.excluded} />
          {children(d)}
        </>
      )}
      <div className="flex justify-between gap-3 pt-2">
        <Button onClick={onBack}>Back to review</Button>
        <Button onClick={onFinish}>Redact another file</Button>
      </div>
    </section>
  );
}

export function DownloadCards({
  safe,
  confidential,
}: {
  safe: ReactNode;
  confidential: ReactNode;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section aria-labelledby="safe-heading" className="rounded-2xl border border-border-soft p-5">
        <h2 id="safe-heading" className="flex items-center justify-between font-semibold">
          Safe to share
          <span className="rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
            Internal
          </span>
        </h2>
        <div className="mt-4 space-y-3 text-sm">{safe}</div>
      </section>
      <section
        aria-labelledby="private-heading"
        className="rounded-2xl border border-danger/50 bg-danger-soft/40 p-5"
      >
        <h2 id="private-heading" className="flex items-center justify-between font-semibold">
          Keep private
          <span className="rounded-full bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger">
            Confidential
          </span>
        </h2>
        <div className="mt-4 space-y-3 text-sm">{confidential}</div>
      </section>
    </div>
  );
}
