// A page of the redacted or original PDF, rendered on this computer.
// Images arrive as object URLs (the request needs the client header) and
// are freed as soon as they are replaced.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../../api";
import { IconButton, Notice, Skeleton } from "../ui";

export function PdfPreview({
  jobId,
  pageCount,
  version,
  initialPage = 1,
  focus,
}: {
  jobId: string;
  pageCount: number;
  /** Bumped on every rebuild, so the redacted page refetches. */
  version: number;
  initialPage?: number;
  /** A page to jump to; ``seq`` changes on every selection. */
  focus?: { page: number; seq: number } | null;
}) {
  const [page, setPage] = useState(initialPage);
  useEffect(() => {
    if (focus && focus.page >= 1 && focus.page <= pageCount) setPage(focus.page);
    // Keyed on the selection, so paging by hand afterwards sticks.
  }, [focus?.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  const [which, setWhich] = useState<"redacted" | "original">("redacted");
  const image = useQuery({
    queryKey: ["pdf-page", jobId, page, which, which === "redacted" ? version : 0],
    queryFn: () => api.pdf.page(jobId, page, which),
    gcTime: 0,
    staleTime: Infinity,
  });
  const url = image.data;
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <IconButton
          icon="chevron-left"
          label="Previous page"
          className="border border-border-soft bg-card shadow-sm"
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
        />
        <label className="inline-flex items-center gap-1">
          Page
          <select
            value={page}
            onChange={(e) => setPage(Number(e.target.value))}
            className="rounded-lg border border-border bg-card shadow-sm px-2 py-1"
          >
            {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          of {pageCount}
        </label>
        <IconButton
          icon="chevron-right"
          label="Next page"
          className="border border-border-soft bg-card shadow-sm"
          disabled={page >= pageCount}
          onClick={() => setPage((p) => p + 1)}
        />
        <div role="group" aria-label="Version" className="ml-auto flex rounded-lg bg-surface-2 p-0.5">
          {(["redacted", "original"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={which === v}
              onClick={() => setWhich(v)}
              className={`rounded-md px-3 py-1 text-xs capitalize transition ${which === v ? "bg-card font-medium text-text shadow-sm" : "text-muted hover:text-text"}`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      {image.error ? (
        <Notice tone="danger">{image.error.message}</Notice>
      ) : !url ? (
        <Skeleton label="Rendering page..." lines={8} />
      ) : (
        <div className="card max-h-[70vh] overflow-auto bg-surface-2 p-3">
          <img
            src={url}
            alt={`Page ${page} of ${pageCount}, ${which}`}
            className="mx-auto block max-w-full bg-white shadow-md"
          />
        </div>
      )}
      {which === "original" && (
        <p className="text-xs text-muted">The original, not redacted. Check it against the redacted page.</p>
      )}
    </div>
  );
}
