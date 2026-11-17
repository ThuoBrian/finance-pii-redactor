// The findings list: one row per distinct term, likeliest mistakes first.
// A ticked row is hidden in the download; unticking leaves the term visible
// in this document only. Filtering and searching never change a row's tick.
//
// Each row has two targets: the tick box, and the term itself, which selects
// it so the side panel shows where it is. ↑/↓ move between rows (and select
// them); Space ticks or unticks, as on any tick box.
import { useMemo, useRef, useState, type KeyboardEvent } from "react";

import type { ReviewRow, SourceFilter } from "../../api";
import { Button, Notice } from "../ui";

// Filter, search and bulk buttons help only once the list scrolls.
const LONG_LIST = 12;
// The filter value for "Worth a closer look": model guesses with a hint.
export const HINTED = "__hinted__";
const MODEL_GUESS = "Model guess";

const CLEAN_RUN =
  "Nothing here is a guess. Every term came from your master list, words you " +
  "typed, a table column you chose, or a strict pattern such as an email or " +
  "account number.";

function isHinted(row: ReviewRow): boolean {
  return row.source === MODEL_GUESS && row.hint !== "";
}

export function visibleRows(
  rows: ReviewRow[],
  source: string | null,
  search: string,
): ReviewRow[] {
  const needle = search.trim().toLocaleLowerCase();
  return rows.filter(
    (r) =>
      (source === null || (source === HINTED ? isHinted(r) : r.source === source)) &&
      (!needle || r.term.toLocaleLowerCase().includes(needle)),
  );
}

export function ReviewList({
  rows,
  filters,
  clean,
  pending,
  onChange,
  selected = null,
  onSelect,
}: {
  rows: ReviewRow[];
  filters: SourceFilter[];
  clean: boolean;
  /** Keys of terms to leave visible (not yet necessarily applied). */
  pending: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  const [source, setSource] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [details, setDetails] = useState(false);
  const [showClean, setShowClean] = useState(false);
  const shown = useMemo(() => visibleRows(rows, source, search), [rows, source, search]);
  const boxes = useRef<(HTMLInputElement | null)[]>([]);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted">
        Nothing to review: no names or private details were found. If you
        expected some, check the options you scanned with.
      </p>
    );
  }

  const toggle = (key: string) => {
    const next = new Set(pending);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(next);
  };
  const setAll = (hide: boolean) => {
    const next = new Set(pending);
    for (const r of shown) {
      if (hide) next.delete(r.key);
      else next.add(r.key);
    }
    onChange(next);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const current = boxes.current.findIndex((b) => b === document.activeElement);
    if (current < 0) return;
    e.preventDefault();
    const next = Math.min(shown.length - 1, Math.max(0, current + (e.key === "ArrowDown" ? 1 : -1)));
    boxes.current[next]?.focus();
  };

  if (clean && !showClean) {
    return (
      <div className="space-y-3">
        <Notice tone="success">{CLEAN_RUN}</Notice>
        <Button onClick={() => setShowClean(true)}>Review anyway</Button>
      </div>
    );
  }

  const long = rows.length > LONG_LIST;
  const hintedCount = rows.filter(isHinted).length;
  const chips = [
    { label: "All", source: null as string | null, count: rows.length },
    ...(hintedCount ? [{ label: "Worth a closer look", source: HINTED, count: hintedCount }] : []),
    ...filters,
  ];

  return (
    <div className="flex min-h-0 flex-col gap-3">
      {long && (
        <div className="flex flex-col gap-2">
          <div role="group" aria-label="Show" className="flex flex-wrap gap-1.5">
            {chips.map((f) => (
              <button
                key={f.label}
                type="button"
                aria-pressed={source === f.source}
                onClick={() => setSource(f.source)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  source === f.source
                    ? "border-primary bg-primary text-white"
                    : "border-border-soft hover:bg-surface"
                }`}
              >
                {f.label} ({f.count})
              </button>
            ))}
          </div>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Find a term"
            aria-label="Find a term"
            className="w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm"
          />
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <label className="inline-flex items-center gap-2 text-muted">
          <input
            type="checkbox"
            checked={details}
            onChange={(e) => setDetails(e.target.checked)}
          />
          Show details
        </label>
        <span className="hidden text-muted sm:inline" aria-hidden>
          ↑ ↓ move · Space ticks or unticks
        </span>
        {long && (
          <span className="flex gap-1">
            <Button
              className="!px-2.5 !py-1 text-xs"
              disabled={!shown.length}
              onClick={() => setAll(false)}
            >
              Untick all shown ({shown.length})
            </Button>
            <Button
              className="!px-2.5 !py-1 text-xs"
              disabled={!shown.length}
              onClick={() => setAll(true)}
            >
              Tick all shown ({shown.length})
            </Button>
          </span>
        )}
      </div>

      <ul
        aria-label="Detected terms"
        onKeyDown={onKeyDown}
        className="max-h-[55vh] divide-y divide-border-soft overflow-y-auto rounded-xl border border-border-soft"
      >
        {shown.map((r, i) => {
          const hidden = !pending.has(r.key);
          const isSelected = selected === r.key;
          return (
            <li
              key={r.key}
              className={`flex items-start gap-3 px-3 py-2.5 ${
                isSelected ? "bg-surface shadow-[inset_3px_0_0_var(--primary)]" : "hover:bg-surface"
              }`}
            >
              <input
                ref={(el) => {
                  boxes.current[i] = el;
                }}
                type="checkbox"
                className="mt-1"
                checked={hidden}
                onChange={() => toggle(r.key)}
                onFocus={() => onSelect?.(r.key)}
                aria-label={`Hide ${r.term}`}
                aria-describedby={`why-${r.key}`}
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => onSelect?.(r.key)}
                className="min-w-0 flex-1 text-left"
              >
                <span
                  className={`block break-words font-medium ${hidden ? "" : "text-muted line-through"}`}
                >
                  {r.term}
                </span>
                <span id={`why-${r.key}`} className="block text-xs text-muted">
                  {r.why}
                  {!hidden && " · left visible"}
                </span>
                {details && (
                  <span className="mt-0.5 block text-xs text-muted">
                    {r.kind} · {r.source} · confidence {r.confidence.toFixed(2)} ·{" "}
                    {r.occurrences}×
                  </span>
                )}
              </button>
            </li>
          );
        })}
        {shown.length === 0 && (
          <li className="px-3 py-4 text-sm text-muted">No terms match.</li>
        )}
      </ul>
    </div>
  );
}
