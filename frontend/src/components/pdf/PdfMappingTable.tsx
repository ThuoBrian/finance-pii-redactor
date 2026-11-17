// The label mapping on screen: which name each [001] stands for. Names are
// shown here for the reviewer only; the label mapping file has none.
import { plural, type PdfMappingRow } from "../../api";
import { FRAME, TD, TH } from "../review/Tables";
import { Notice } from "../ui";
import { SortHeader, TableSearch, useTableControls } from "../useTableControls";

const COLUMNS = {
  label: (r: PdfMappingRow) => r.label,
  name: (r: PdfMappingRow) => r.original_name,
  id: (r: PdfMappingRow) => r.internal_id,
  note: (r: PdfMappingRow) => r.flagged,
};

export function PdfMappingTable({ rows, blackout }: { rows: PdfMappingRow[]; blackout: boolean }) {
  const t = useTableControls(rows, COLUMNS, (r) => `${r.label} ${r.original_name} ${r.internal_id}`);
  if (blackout) {
    return <p className="text-sm text-muted">Black out leaves nothing to decode, so there is no mapping.</p>;
  }
  if (rows.length === 0) {
    return <p className="text-sm text-muted">Nothing was replaced with a label, so there is no mapping.</p>;
  }
  const suggested = rows.filter((r) => r.possible_match).length;
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted">
        Names are shown here for your review only. The label mapping file on the
        Download step contains no names.
      </p>
      {suggested > 0 && (
        <Notice>
          Close master-list match for {plural(suggested, "unresolved item")}, see
          “Possible match”. A hint only; it was not applied.
        </Notice>
      )}
      <div>
        {t.searchable && (
          <TableSearch value={t.query} onChange={t.setQuery} label="Find a label, name or ID" />
        )}
        <div className={FRAME}>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <SortHeader className={TH} label="Label" column="label" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Original name" column="name" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Internal ID" column="id" sort={t.sort} onSort={t.toggle} />
                <SortHeader className={TH} label="Note" column="note" sort={t.sort} onSort={t.toggle} />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-soft">
              {t.shown.map((r) => (
                <tr key={r.label}>
                  <td className={`${TD} font-mono text-xs`}>{r.label}</td>
                  <td className={TD}>
                    {r.original_name}
                    <span className="block text-xs text-muted">{r.kind}</span>
                  </td>
                  <td className={`${TD} font-mono text-xs`}>{r.internal_id || "—"}</td>
                  <td className={`${TD} text-xs text-muted`}>
                    {r.flagged}
                    {r.possible_match && <span className="block">Possible match: {r.possible_match}</span>}
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
