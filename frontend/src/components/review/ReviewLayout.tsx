// The Review step's frame, shared by every format: findings on the left, a
// side panel on the right, and a sticky footer that holds the only actions.
// Continue waits while changes are not applied: building the download from
// an older choice could leave visible a term the reviewer re-ticked.
//
// Selecting a term (click, or moving to it with the arrow keys) points the
// side panel at where it is; "place 1 of N" steps through its occurrences.
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { plural, type ReviewRow, type SourceFilter } from "../../api";
import { Toast } from "../Toast";
import { Icon } from "../Icon";
import { Button, IconButton, Notice } from "../ui";
import { ReviewList } from "./ReviewList";

export type Panel = { id: string; label: string; content: ReactNode };

/** The selected term and which of its occurrences to show. ``seq`` changes on
 * every selection, so selecting the same place again still re-focuses it. */
export type Selection = { key: string; place: number; seq: number } | null;

export function ReviewLayout({
  heading,
  summary,
  rows,
  filters,
  clean,
  applied,
  carried,
  panels,
  applying,
  applyError,
  onApply,
  onBack,
  onContinue,
  additions,
  hold,
  occurrences = [],
  focusPanel,
}: {
  heading: string;
  summary: string;
  rows: ReviewRow[];
  filters: SourceFilter[];
  clean: boolean;
  applied: string[];
  carried: string[];
  panels: (selection: Selection) => Panel[];
  applying: boolean;
  applyError: string | null;
  onApply: (excluded: string[]) => void;
  onBack: () => void;
  onContinue: () => void;
  /** Extra controls folded under "Add something the tool missed". */
  additions?: ReactNode;
  /** Why Continue must wait besides unapplied ticks (e.g. words not added). */
  hold?: string | null;
  /** Every place a term occurs (by review ``key``); enables "place i of N". */
  occurrences?: { key: string }[];
  /** The panel to show when a term is selected. */
  focusPanel?: string;
}) {
  const appliedSet = useMemo(() => new Set(applied), [applied]);
  const [pending, setPending] = useState<Set<string>>(appliedSet);
  const [selection, setSelection] = useState<Selection>(null);
  const resolved = panels(selection);
  const [panel, setPanel] = useState(resolved[0]?.id ?? "");
  const [justApplied, setJustApplied] = useState(false);
  const dismissToast = useCallback(() => setJustApplied(false), []);

  // A new result (scan or apply) resets the pending choice to what is applied.
  useEffect(() => setPending(new Set(appliedSet)), [appliedSet]);

  const changes =
    [...pending].filter((k) => !appliedSet.has(k)).length +
    [...appliedSet].filter((k) => !pending.has(k)).length;
  const hidden = rows.length - [...pending].filter((k) => rows.some((r) => r.key === k)).length;

  const select = (key: string, place = 0) => {
    setSelection((cur) => ({ key, place, seq: (cur?.seq ?? 0) + 1 }));
    if (focusPanel) setPanel(focusPanel);
  };
  const selectedRow = selection ? rows.find((r) => r.key === selection.key) : undefined;
  const places = selection ? occurrences.filter((o) => o.key === selection.key).length : 0;

  return (
    <section aria-labelledby="review-heading" className="pb-24">
      <h1 id="review-heading" tabIndex={-1} className="text-3xl font-semibold tracking-tight outline-none">
        {heading}
      </h1>
      {summary && <p className="mt-1 text-muted">{summary}</p>}

      {carried.length > 0 && (
        <Notice className="mt-4">
          Kept {plural(carried.length, "term")} you unticked last time:{" "}
          {carried.join(", ")}. {carried.length === 1 ? "It stays" : "They stay"} visible
          in this file. Tick {carried.length === 1 ? "it" : "them"} again and apply to
          hide {carried.length === 1 ? "it" : "them"}.
        </Notice>
      )}
      {justApplied && changes === 0 && !applying && !applyError && (
        <Toast onClose={dismissToast}>
          Rebuilt the file.{" "}
          {applied.length
            ? `${plural(applied.length, "term")} ${applied.length === 1 ? "is" : "are"} left visible.`
            : "Every detected term is hidden."}
        </Toast>
      )}
      {applyError && (
        <Notice tone="danger" className="mt-4">
          {applyError}
        </Notice>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="min-w-0">
          <p className="mb-4 text-sm leading-relaxed text-muted">
            Ticked terms are hidden in your download; the likeliest mistakes are
            at the top. Untick anything that is not a name or private detail,
            then apply. Click a term to see where it is. This fixes this file
            only: fix the master list to stop a wrong name coming back.
          </p>
          <ReviewList
            rows={rows}
            filters={filters}
            clean={clean}
            pending={pending}
            selected={selection?.key ?? null}
            onSelect={(key) => select(key)}
            onChange={(next) => {
              setJustApplied(false);
              setPending(next);
            }}
          />
          {additions && (
            <details className="card group mt-4 overflow-hidden" open={Boolean(hold) || undefined}>
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-1 px-4 py-3 text-sm font-medium transition hover:bg-surface [&::-webkit-details-marker]:hidden">
                <Icon
                  name="chevron-right"
                  className="h-4 w-4 text-muted transition-transform duration-150 group-open:rotate-90"
                />
                Add something the tool missed{" "}
                <span className="font-normal text-muted">(most files need nothing here)</span>
              </summary>
              <div className="border-t border-border-soft px-4 py-4">{additions}</div>
            </details>
          )}
        </div>
        <div className="min-w-0">
          {selection && selectedRow && places > 0 && (
            <div
              className="mb-3 flex items-center gap-1 rounded-xl border border-primary/25 bg-primary-soft py-1.5 pl-3.5 pr-1.5 text-sm"
              aria-live="polite"
            >
              <span className="min-w-0 flex-1 truncate">
                <strong>{selectedRow.term}</strong>
                <span className="text-muted">
                  {" "}
                  · place {selection.place + 1} of {places}
                </span>
              </span>
              <IconButton
                icon="chevron-left"
                label="Previous place"
                disabled={selection.place <= 0}
                onClick={() => select(selection.key, selection.place - 1)}
                className="hover:bg-card"
              />
              <IconButton
                icon="chevron-right"
                label="Next place"
                disabled={selection.place >= places - 1}
                onClick={() => select(selection.key, selection.place + 1)}
                className="hover:bg-card"
              />
              <IconButton
                icon="x"
                label="Clear selection"
                onClick={() => setSelection(null)}
                className="hover:bg-card"
              />
            </div>
          )}
          <div
            role="tablist"
            aria-label="Details"
            className="mb-3 flex gap-0.5 overflow-x-auto rounded-xl bg-surface-2 p-1"
          >
            {resolved.map((p) => (
              <button
                key={p.id}
                type="button"
                role="tab"
                id={`tab-${p.id}`}
                aria-selected={panel === p.id}
                aria-controls={`panel-${p.id}`}
                onClick={() => setPanel(p.id)}
                className={`flex-1 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm transition ${
                  panel === p.id
                    ? "bg-card font-medium text-text shadow-sm"
                    : "text-muted hover:text-text"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {resolved.map((p) =>
            p.id === panel ? (
              <div key={p.id} role="tabpanel" id={`panel-${p.id}`} aria-labelledby={`tab-${p.id}`}>
                {p.content}
              </div>
            ) : null,
          )}
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-border-soft bg-card/90 shadow-up backdrop-blur-md backdrop-saturate-150">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <p className="tabular text-sm" aria-live="polite">
            <strong>{plural(hidden, "term")}</strong> hidden
            {rows.length - hidden > 0 && ` · ${rows.length - hidden} left visible`}
            {changes > 0 && (
              <span className="text-warn"> · {plural(changes, "change")} not applied</span>
            )}
            {hold && changes === 0 && <span className="text-warn"> · {hold}</span>}
          </p>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button onClick={onBack}>Change settings</Button>
            <Button
              variant={changes ? "primary" : "secondary"}
              disabled={!changes || applying}
              onClick={() => {
                setJustApplied(true);
                onApply([...pending].sort());
              }}
            >
              {applying ? "Applying..." : changes ? `Apply changes (${changes})` : "Apply changes"}
            </Button>
            <Button
              variant={changes ? "secondary" : "primary"}
              disabled={changes > 0 || Boolean(hold) || applying}
              title={changes ? "Apply or undo your changes first" : (hold ?? undefined)}
              onClick={onContinue}
            >
              Continue to download
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
