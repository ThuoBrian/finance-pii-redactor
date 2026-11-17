// The Download step: its frame, the two cards and the buttons in them.
// Sorting files by who may see them is the point of this step: the card a
// file sits in is its classification.
import { useMutation, type UseQueryResult } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { downloadFile, plural } from "../api";
import { Icon } from "./Icon";
import { Badge, Button, Notice, Skeleton } from "./ui";

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
        <Icon name={done ? "check" : "download"} className="h-4 w-4" />
        {download.isPending ? "Preparing..." : label}
      </Button>
      {done && !download.isPending && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-success" role="status">
          <Icon name="circle-check" className="mt-px h-3.5 w-3.5" />
          Downloaded. You can download it again if you need another copy.
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
    <section aria-labelledby="download-heading" className="mx-auto max-w-4xl space-y-5">
      <h1 tabIndex={-1} id="download-heading" className="text-3xl font-semibold tracking-tight">
        Download
      </h1>
      {info.error && <Notice tone="danger">{info.error.message}</Notice>}
      {!d ? (
        <Skeleton label="Loading..." />
      ) : (
        <>
          <ExclusionWarning excluded={d.excluded} />
          {children(d)}
        </>
      )}
      <div className="flex flex-wrap justify-between gap-3 border-t border-border-soft pt-5">
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
      <section aria-labelledby="safe-heading" className="card flex flex-col p-6">
        <h2 id="safe-heading" className="flex items-center gap-3 font-semibold">
          <span aria-hidden className="flex h-9 w-9 items-center justify-center rounded-lg bg-success-soft text-success">
            <Icon name="shield-check" className="h-5 w-5" />
          </span>
          Safe to share
          <Badge tone="success" className="ml-auto">
            Internal
          </Badge>
        </h2>
        <div className="mt-5 space-y-3 text-sm leading-relaxed">{safe}</div>
      </section>
      <section
        aria-labelledby="private-heading"
        className="card flex flex-col border-danger/40 p-6 shadow-[inset_0_3px_0_var(--danger),var(--shadow-sm)]"
      >
        <h2 id="private-heading" className="flex items-center gap-3 font-semibold">
          <span aria-hidden className="flex h-9 w-9 items-center justify-center rounded-lg bg-danger-soft text-danger">
            <Icon name="lock" className="h-5 w-5" />
          </span>
          Keep private
          <Badge tone="danger" className="ml-auto">
            Confidential
          </Badge>
        </h2>
        <div className="mt-5 space-y-3 text-sm leading-relaxed">{confidential}</div>
      </section>
    </div>
  );
}
