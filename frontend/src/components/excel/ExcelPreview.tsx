// The workbook preview: a block of rows of one tab, redacted or original.
// Changed cells are yellow like the downloaded file, and also start with »
// so the change does not rely on colour alone.
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api, plural } from "../../api";
import { Notice, Spinner } from "../ui";

const MARKER = "» ";

/** Where to point the preview: a tab, and a cell or header in it. */
export type ExcelFocus = {
  tab: number;
  /** 1-based data row; null for a header or tab name. */
  row: number | null;
  /** Original column header; "" for a tab name. */
  column: string;
  place: "cell" | "header" | "tab";
  seq: number;
};

export function ExcelPreview({
  jobId,
  version,
  focus,
}: {
  jobId: string;
  version: number;
  focus?: ExcelFocus | null;
}) {
  const [tab, setTab] = useState(0);
  const [start, setStart] = useState(0);
  const [original, setOriginal] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  // A new selection moves to its tab and row block.
  useEffect(() => {
    if (!focus || focus.tab < 0) return;
    setTab(focus.tab);
    // Any row in the block will do: the server aligns ``start`` to its block.
    if (focus.row !== null) setStart(focus.row - 1);
    else if (focus.place === "header") setStart(0);
    // Keyed on the selection, not the object: the parent rebuilds it on
    // every render, and a manual tab or block change must stick.
  }, [focus?.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = useQuery({
    queryKey: ["excel-preview", jobId, version, tab, start],
    queryFn: () => api.excel.preview(jobId, tab, start),
    placeholderData: keepPreviousData,
  });
  const data = preview.data;

  // Which cell to outline: row -1 is the header. Columns are found by their
  // original header, since a redacted header has a new name.
  const target =
    focus && data && data.tab === focus.tab && focus.place !== "tab"
      ? (() => {
          const c = data.original_columns.indexOf(focus.column);
          if (c < 0) return null;
          if (focus.place === "header") return `-1:${c}`;
          const r = (focus.row ?? 0) - 1 - data.start;
          return r >= 0 && r < data.rows.length ? `${r}:${c}` : null;
        })()
      : null;

  useEffect(() => {
    if (!target) return;
    const cell = scroller.current?.querySelector<HTMLElement>('[data-focus="true"]');
    cell?.scrollIntoView?.({ block: "center", inline: "center" });
  }, [target, focus?.seq]);

  if (preview.error) return <Notice tone="danger">{preview.error.message}</Notice>;
  if (!data) return <Spinner label="Loading preview..." />;

  const marked = new Set(data.marked.map(([r, c]) => `${r}:${c}`));
  const columns = original ? data.original_columns : data.columns;
  const rows = original ? data.original_rows : data.rows;
  const end = Math.min(data.start + data.page_size, data.total_rows);
  const blocks = Math.ceil(data.total_rows / data.page_size);

  const outline = (key: string) =>
    key === target ? "outline outline-2 outline-offset-[-2px] outline-[var(--primary)]" : "";
  const cell = (text: string, key: string) =>
    marked.has(key) ? (
      <span className="rounded bg-[#FFFF00] px-1 text-[#1a1a1a]">
        {MARKER}
        {text}
      </span>
    ) : (
      text
    );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {data.tabs.length > 1 && (
          <select
            aria-label="Tab to preview"
            value={tab}
            onChange={(e) => {
              setTab(Number(e.target.value));
              setStart(0);
            }}
            className="rounded-lg border border-border bg-bg px-2 py-1"
          >
            {data.tabs.map((name, i) => (
              <option key={name} value={i}>
                {name}
              </option>
            ))}
          </select>
        )}
        {blocks > 1 && (
          <select
            aria-label="Rows to preview"
            value={data.start}
            onChange={(e) => setStart(Number(e.target.value))}
            className="rounded-lg border border-border bg-bg px-2 py-1"
          >
            {Array.from({ length: blocks }, (_, i) => i * data.page_size).map((s) => (
              <option key={s} value={s}>
                Rows {(s + 1).toLocaleString()} to{" "}
                {Math.min(s + data.page_size, data.total_rows).toLocaleString()}
              </option>
            ))}
          </select>
        )}
        <div role="group" aria-label="Version" className="ml-auto flex rounded-lg border border-border-soft p-0.5">
          {[
            ["Redacted", false],
            ["Original", true],
          ].map(([label, value]) => (
            <button
              key={String(label)}
              type="button"
              aria-pressed={original === value}
              onClick={() => setOriginal(Boolean(value))}
              className={`rounded-md px-2.5 py-1 text-xs ${original === value ? "bg-surface font-medium" : "text-muted"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {original && (
        <p className="text-xs text-muted">The original, not redacted. Check it against the redacted view.</p>
      )}
      {blocks > 1 && (
        <p className="text-xs text-muted">
          Showing rows {(data.start + 1).toLocaleString()} to {end.toLocaleString()} of{" "}
          {data.total_rows.toLocaleString()}
          {data.elsewhere > 0 &&
            `; ${plural(data.elsewhere, "changed cell")} in rows not shown`}
          . The download has every row.
        </p>
      )}

      <div ref={scroller} className="max-h-[60vh] overflow-auto rounded-xl border border-border-soft">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              {columns.map((name, c) => (
                <th
                  key={c}
                  scope="col"
                  data-focus={target === `-1:${c}` || undefined}
                  className={`sticky top-0 whitespace-nowrap bg-surface px-3 py-2 text-left text-xs font-semibold ${outline(`-1:${c}`)}`}
                >
                  {cell(name, `-1:${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-soft">
            {rows.map((row, r) => (
              <tr key={r}>
                {row.map((value, c) => (
                  <td
                    key={c}
                    data-focus={target === `${r}:${c}` || undefined}
                    className={`max-w-xs truncate whitespace-nowrap px-3 py-1.5 ${outline(`${r}:${c}`)}`}
                    title={value}
                  >
                    {cell(value, `${r}:${c}`)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
