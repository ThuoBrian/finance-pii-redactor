// Read-only tables for the Review step's side panel: the name -> code mapping
// and every place a term was found. Names show on the user's own screen only.
// Long tables get a search box; every column header sorts.
import type { MappingRow, Occurrence, TextOccurrence } from "../../api";
import { plural } from "../../api";
import { Notice } from "../ui";
import { SortHeader, TableSearch, useTableControls } from "../useTableControls";

export const TH = "sticky top-0 bg-surface px-3 py-2 text-left text-xs font-semibold";
export const TD = "px-3 py-2 align-top";
export const FRAME = "max-h-[55vh] overflow-auto rounded-xl border border-border-soft";

const MAPPING_COLUMNS = {
  name: (r: MappingRow) => r.original_name,
  code: (r: MappingRow) => r.pseudonym,
  kind: (r: MappingRow) => r.kind,
  note: (r: MappingRow) => (r.flagged ? 1 : 0),
};

export function MappingTable({ rows }: { rows: MappingRow[] }) {
  const t = useTableControls(rows, MAPPING_COLUMNS, (r) => `${r.original_name} ${r.pseudonym}`);
  if (rows.length === 0) {
    return <p className="text-sm text-muted">No names were replaced, so there is no mapping.</p>;
  }
  const flagged = rows.filter((r) => r.flagged).length;
  const suggested = rows.filter((r) => r.possible_match).length;
  return (
    <div className="space-y-3">
      {flagged > 0 && (
        <Notice>
          Not in the master list: {plural(flagged, "name")}. Each got a flagged
          auto-generated ID. If correct, add them to the master list with a
          curated ID.
        </Notice>
      )}
      {suggested > 0 && (
        <Notice>
          Close master-list match for {plural(suggested, "flagged name")}, see
          “Possible match”. A hint only; it was not applied.
        </Notice>
      )}
      <div>
        {t.searchable && (
          <TableSearch value={t.query} onChange={t.setQuery} label="Find a name or code" />
        )}
        <div className={FRAME}>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <SortHeader className={TH} label="Original name" column="name" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Code" column="code" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Kind" column="kind" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Note" column="note" sort={t.sort} onSort={t.toggle} />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-soft">
              {t.shown.map((r) => (
                <tr key={`${r.original_name}|${r.pseudonym}`}>
                  <td className={TD}>{r.original_name}</td>
                  <td className={`${TD} font-mono text-xs`}>{r.pseudonym}</td>
                  <td className={`${TD} text-muted`}>{r.kind}</td>
                  <td className={`${TD} text-xs text-muted`}>
                    {r.flagged ? "Not in master list" : ""}
                    {r.possible_match && (
                      <span className="block">Possible match: {r.possible_match}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const OCCURRENCE_COLUMNS = {
  tab: (r: Occurrence) => r.sheet,
  row: (r: Occurrence) => r.row ?? 0,
  column: (r: Occurrence) => r.column,
  term: (r: Occurrence) => r.term,
};

export function OccurrenceTable({ rows }: { rows: Occurrence[] }) {
  const t = useTableControls(rows, OCCURRENCE_COLUMNS, (r) => `${r.term} ${r.sheet} ${r.column}`);
  if (rows.length === 0) return <p className="text-sm text-muted">Nothing was found.</p>;
  return (
    <div>
      {t.searchable && <TableSearch value={t.query} onChange={t.setQuery} label="Find a term" />}
      <div className={FRAME}>
        <table className="w-full text-sm">
          <thead>
            <tr>
              <SortHeader className={TH} label="Tab" column="tab" sort={t.sort} onSort={t.toggle} />
              <SortHeader className={TH} label="Row" column="row" sort={t.sort} onSort={t.toggle} />
              <SortHeader className={TH} label="Column" column="column" sort={t.sort} onSort={t.toggle} />
              <SortHeader className={TH} label="Term" column="term" sort={t.sort} onSort={t.toggle} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-soft">
            {t.shown.map((r, i) => (
              <tr key={i}>
                <td className={TD}>{r.sheet}</td>
                <td className={`${TD} text-muted`}>{r.row ?? "—"}</td>
                <td className={`${TD} text-muted`}>{r.column}</td>
                <td className={TD}>{r.term}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const TEXT_COLUMNS = {
  location: (r: TextOccurrence) => r.location,
  term: (r: TextOccurrence) => r.term,
  kind: (r: TextOccurrence) => r.kind,
};

export function TextOccurrenceTable({
  rows: allRows,
  locationLabel,
  onlyKey = null,
}: {
  rows: TextOccurrence[];
  locationLabel: string;
  /** Show only this term's occurrences (the selected review row). */
  onlyKey?: string | null;
}) {
  const rows = onlyKey ? allRows.filter((r) => r.key === onlyKey) : allRows;
  const t = useTableControls(rows, TEXT_COLUMNS, (r) => r.term);
  if (rows.length === 0) return <p className="text-sm text-muted">Nothing was found.</p>;
  return (
    <div>
      {t.searchable && <TableSearch value={t.query} onChange={t.setQuery} label="Find a term" />}
      <div className={FRAME}>
        <table className="w-full text-sm">
          <thead>
            <tr>
              <SortHeader className={TH} label={locationLabel} column="location" sort={t.sort} onSort={t.toggle} />
              <SortHeader className={TH} label="Term" column="term" sort={t.sort} onSort={t.toggle} />
              <SortHeader className={TH} label="Kind" column="kind" sort={t.sort} onSort={t.toggle} />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-soft">
            {t.shown.map((r, i) => (
              <tr key={i}>
                <td className={`${TD} text-muted`}>{r.location}</td>
                <td className={TD}>{r.term}</td>
                <td className={`${TD} text-muted`}>{r.kind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
