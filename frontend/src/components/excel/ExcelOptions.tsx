// Excel Options: the summary and one button up front; tabs, columns,
// confidence and kinds of information fold under "Customize".
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api, type ExcelOptions as Options, type ExcelScanRequest } from "../../api";
import { Customize, DetectionFields, toggleIn } from "../DetectionFields";
import { InfoTip } from "../InfoTip";
import { OptionsFooter } from "../OptionsFooter";
import { Notice } from "../ui";
import { useDebounced } from "../useDebounced";

export type ExcelChoices = ExcelScanRequest;

export function defaultChoices(options: Options): ExcelChoices {
  return {
    tabs: options.tabs.map((t) => t.name),
    columns: Object.fromEntries(options.tabs.map((t) => [t.name, t.default_columns])),
    entities: options.entities.map((e) => e.code),
    threshold: options.threshold.default,
  };
}

function nameSummary(names: string[], shown = 2): string {
  const rest = names.length - shown;
  const head = names.slice(0, shown).join(", ");
  return rest > 0 ? `${head} + ${rest.toLocaleString()} more` : head;
}

export function ExcelOptions({
  jobId,
  options,
  choices,
  onChange,
  onScan,
  onBack,
  busy,
  error,
  notice = null,
  recommended,
}: {
  jobId: string;
  options: Options;
  choices: ExcelChoices;
  onChange: (next: ExcelChoices) => void;
  onScan: () => void;
  onBack: () => void;
  busy: boolean;
  error: string | null;
  /** A neutral note, e.g. that a scan was cancelled. */
  notice?: string | null;
  /** True when the choices are the recommended defaults. */
  recommended: boolean;
}) {
  const [columnTab, setColumnTab] = useState(choices.tabs[0] ?? "");
  const selectedTabs = options.tabs.filter((t) => choices.tabs.includes(t.name));
  const shownTab =
    selectedTabs.find((t) => t.name === columnTab) ?? selectedTabs[0] ?? null;
  const noColumns = selectedTabs.filter((t) => !(choices.columns[t.name] ?? []).length);
  const problem = !selectedTabs.length
    ? "Choose at least one tab to scan, under Customize."
    : noColumns.length === selectedTabs.length
      ? "Choose at least one column to scan, under Customize."
      : !choices.entities.length
        ? "Choose at least one kind of information to hide, under Customize."
        : null;

  // Memoized: a new object every render would restart the debounce timer
  // and re-render Options every 400 ms for as long as it is open.
  const current = useMemo(
    () => ({ tabs: choices.tabs, columns: choices.columns }),
    [choices.tabs, choices.columns],
  );
  const selection = useDebounced(current, 400);
  const estimate = useQuery({
    queryKey: ["excel-estimate", jobId, selection],
    queryFn: () => api.excel.estimate(jobId, selection),
    enabled: !problem,
  });

  const setTabs = (tabs: string[]) => onChange({ ...choices, tabs });

  return (
    <section aria-labelledby="options-heading" className="mx-auto max-w-2xl">
      <h1 tabIndex={-1} id="options-heading" className="text-3xl font-semibold tracking-tight">
        Ready to redact
      </h1>
      <p className="mt-2 leading-relaxed text-muted">{options.summary}</p>

      <Customize hint="tabs and columns, kinds of information, confidence">
          {options.tabs.length > 1 && (
            <fieldset>
              <legend className="inline-flex items-center text-sm font-medium">
                Tabs to scan
                <InfoTip label="Tabs to scan">
                  Tabs you leave out are not scanned, and they are not in the
                  downloaded file either.
                </InfoTip>
              </legend>
              <div className="mt-2 flex flex-wrap gap-2">
                {options.tabs.map((t) => (
                  <label
                    key={t.name}
                    className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border-soft bg-card px-3 py-2 text-sm shadow-sm transition hover:bg-surface has-[:checked]:border-primary/60 has-[:checked]:bg-primary-soft"
                  >
                    <input
                      type="checkbox"
                      checked={choices.tabs.includes(t.name)}
                      onChange={() => setTabs(toggleIn(choices.tabs, t.name))}
                    />
                    {t.name}
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {shownTab && (
            <fieldset>
              <legend className="inline-flex items-center text-sm font-medium">
                Columns to scan
                <InfoTip label="Columns to scan">
                  Numeric and date columns are left out by default. Add a
                  numeric column if it holds account or M-Pesa numbers. Column
                  headers are always checked.
                </InfoTip>
              </legend>
              {selectedTabs.length > 1 && (
                <label className="mt-2 block text-sm">
                  <span className="sr-only">Which tab's columns</span>
                  <select
                    value={shownTab.name}
                    onChange={(e) => setColumnTab(e.target.value)}
                    className="rounded-lg border border-border bg-card shadow-sm px-3 py-1.5 text-sm"
                  >
                    {selectedTabs.map((t) => (
                      <option key={t.name} value={t.name}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="mt-2 grid max-h-56 grid-cols-1 gap-1 overflow-y-auto sm:grid-cols-2">
                {shownTab.columns.map((label, i) => (
                  <label
                    key={i}
                    className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-surface"
                  >
                    <input
                      type="checkbox"
                      checked={(choices.columns[shownTab.name] ?? []).includes(i)}
                      onChange={() =>
                        onChange({
                          ...choices,
                          columns: {
                            ...choices.columns,
                            [shownTab.name]: toggleIn(
                              choices.columns[shownTab.name] ?? [],
                              i,
                            ).sort((a, b) => a - b),
                          },
                        })
                      }
                    />
                    <span className="truncate" title={label}>
                      {label}
                    </span>
                  </label>
                ))}
              </div>
              {noColumns.length > 0 && noColumns.length < selectedTabs.length && (
                <p className="mt-2 text-xs text-muted">
                  No columns chosen in {nameSummary(noColumns.map((t) => t.name))}:
                  only the headers and tab name are checked there, and its cells
                  go into the download as they are.
                </p>
              )}
            </fieldset>
          )}

          <DetectionFields
            options={options}
            choices={choices}
            onChange={(next) => onChange({ ...choices, ...next })}
          />
      </Customize>

      {problem && (
        <Notice tone="warn" className="mt-4">
          {problem}
        </Notice>
      )}
      {!problem && estimate.data?.warning && (
        <Notice tone="warn" className="mt-4">
          {estimate.data.warning}
        </Notice>
      )}
      <OptionsFooter
        recommended={recommended}
        busy={busy}
        disabled={Boolean(problem)}
        notice={notice}
        error={error}
        onBack={onBack}
        onScan={onScan}
      />
    </section>
  );
}
