// Search and click-to-sort for the read-only tables in the Review panel.
// Search appears only once a table is long enough to need it.
import { useMemo, useState } from "react";

import { Icon } from "./Icon";

const SEARCH_FROM = 12;

type Sort = { key: string; dir: 1 | -1 } | null;

export function useTableControls<T>(
  rows: T[],
  columns: Record<string, (row: T) => string | number>,
  searchText: (row: T) => string,
) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>(null);
  const shown = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    let out = needle
      ? rows.filter((r) => searchText(r).toLocaleLowerCase().includes(needle))
      : rows;
    const get = sort ? columns[sort.key] : undefined;
    if (sort && get) {
      out = [...out].sort((a, b) => {
        const va = get(a);
        const vb = get(b);
        const order =
          typeof va === "number" && typeof vb === "number"
            ? va - vb
            : String(va).localeCompare(String(vb), undefined, { numeric: true });
        return order * sort.dir;
      });
    }
    return out;
    // columns and searchText are stable descriptions of the table's shape.
  }, [rows, query, sort]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Ascending, then descending, then back to the original order. */
  const toggle = (key: string) =>
    setSort((s) => (s?.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : null));

  return { shown, query, setQuery, sort, toggle, searchable: rows.length > SEARCH_FROM };
}

export function SortHeader({
  label,
  column,
  sort,
  onSort,
  className,
}: {
  label: string;
  column: string;
  sort: Sort;
  onSort: (column: string) => void;
  className: string;
}) {
  const active = sort?.key === column;
  return (
    <th
      className={className}
      aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className="group inline-flex items-center gap-1 hover:text-text"
      >
        {label}
        <Icon
          name={!active ? "chevrons-up-down" : sort.dir === -1 ? "arrow-down" : "arrow-up"}
          className={`h-3 w-3 ${active ? "text-primary" : "opacity-40 group-hover:opacity-80"}`}
        />
      </button>
    </th>
  );
}

export function TableSearch({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <div className="relative mb-2">
      <Icon
        name="search"
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
        aria-label={label}
        className="h-9 w-full rounded-lg border border-border bg-card pl-9 pr-3 text-sm shadow-sm"
      />
    </div>
  );
}
