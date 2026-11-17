// Excel: settings → Review → Download. Stays mounted across the three steps,
// so the choices survive going Back from Review.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, plural, type Job, type Prefs } from "../../api";
import { CrosswalkCard, DownloadButton, DownloadCards, DownloadStep } from "../DownloadCards";
import { MappingTable, OccurrenceTable } from "../review/Tables";
import { ReviewLayout } from "../review/ReviewLayout";
import { ScanProgress } from "../TaskProgress";
import { Button, Notice, Skeleton } from "../ui";
import { useFormatFlow } from "../useFormatFlow";
import { ExcelOptions, defaultChoices, type ExcelChoices } from "./ExcelOptions";
import { ExcelPreview } from "./ExcelPreview";

export function ExcelFlow({
  job,
  step,
  goTo,
  onFinish,
  prefs,
  onPrefs,
  onPending,
}: {
  job: Job;
  step: 1 | 2 | 3;
  goTo: (step: 0 | 1 | 2 | 3) => void;
  onFinish: () => void;
  prefs?: Prefs["excel"];
  onPrefs: (prefs: Prefs["excel"]) => void;
  /** Labels of expected files not yet downloaded for this build. */
  onPending: (missing: string[]) => void;
}) {
  const options = useQuery({
    queryKey: ["excel-options", job.id],
    queryFn: () => api.excel.options(job.id),
  });
  const [choices, setChoices] = useState<ExcelChoices | null>(null);
  const flow = useFormatFlow(job.id, step, goTo, onPending, {
    name: "excel",
    scan: (body: ExcelChoices) => api.excel.scan(job.id, body),
    review: () => api.excel.review(job.id),
    apply: (excluded: string[]) => api.excel.apply(job.id, excluded),
    download: () => api.excel.download(job.id),
    expected: (r) => [
      { kind: "redacted", label: "the redacted workbook" },
      ...(r.mapping.length ? [{ kind: "crosswalk", label: "the name mapping" }] : []),
    ],
  });

  useEffect(() => {
    if (!options.data || choices) return;
    const defaults = defaultChoices(options.data);
    const known = new Set(defaults.entities);
    setChoices(
      prefs
        ? {
            ...defaults,
            threshold: prefs.threshold,
            entities: prefs.entities.filter((e) => known.has(e)),
          }
        : defaults,
    );
  }, [options.data, choices]); // eslint-disable-line react-hooks/exhaustive-deps

  if (step === 1) {
    if (options.error) {
      return (
        <section className="mx-auto max-w-2xl space-y-4">
          <Notice tone="danger">{options.error.message}</Notice>
          <Button onClick={() => goTo(0)}>Back to upload</Button>
        </section>
      );
    }
    if (!options.data || !choices) return <Skeleton label="Reading the workbook..." />;
    if (flow.scanning) {
      return <ScanProgress jobId={job.id} unit="unique value" progress={flow.progress} />;
    }
    const d = defaultChoices(options.data);
    return (
      <ExcelOptions
        jobId={job.id}
        options={options.data}
        choices={choices}
        onChange={(next) => {
          setChoices(next);
          onPrefs({ threshold: next.threshold, entities: next.entities });
        }}
        recommended={
          choices.threshold === d.threshold &&
          choices.entities.length === d.entities.length &&
          choices.tabs.length === d.tabs.length &&
          JSON.stringify(choices.columns) === JSON.stringify(d.columns)
        }
        onScan={() => flow.scan.mutate(choices)}
        onBack={() => goTo(0)}
        busy={flow.scan.isPending}
        error={flow.scanError}
        notice={flow.scanNotice}
      />
    );
  }

  if (flow.review.error) return <Notice tone="danger">{flow.review.error.message}</Notice>;
  const r = flow.review.data;
  if (!r) return <Skeleton label="Loading..." />;

  if (step === 2) {
    return (
      <ReviewLayout
        heading="Review what was found"
        summary={
          r.summary ||
          `${plural(r.entity_count, "term")} found in ${plural(r.cell_count, "cell")}`
        }
        rows={r.rows}
        filters={r.filters}
        clean={r.clean}
        applied={r.applied}
        carried={r.carried}
        applying={flow.apply.isPending}
        applyError={flow.apply.error?.message ?? null}
        onApply={(excluded) => flow.apply.mutate(excluded)}
        onBack={() => goTo(1)}
        onContinue={() => goTo(3)}
        occurrences={r.occurrences}
        focusPanel="preview"
        panels={(selection) => {
          const occurrence = selection
            ? r.occurrences.filter((o) => o.key === selection.key)[selection.place]
            : undefined;
          const focus =
            selection && occurrence
              ? {
                  tab: r.tabs.indexOf(occurrence.sheet),
                  row: occurrence.row,
                  column: occurrence.column_name,
                  place: occurrence.place,
                  seq: selection.seq,
                }
              : null;
          return [
            {
              id: "preview",
              label: "Preview",
              content: <ExcelPreview jobId={job.id} version={flow.version} focus={focus} />,
            },
            {
              id: "mapping",
              label: `Mapping (${r.mapping.length})`,
              content: <MappingTable rows={r.mapping} />,
            },
            {
              id: "where",
              label: "Where found",
              content: <OccurrenceTable rows={r.occurrences} />,
            },
          ];
        }}
      />
    );
  }

  return (
    <DownloadStep info={flow.info} onBack={() => goTo(2)} onFinish={onFinish}>
      {(d) => (
        <>
          {d.left_out.length > 0 && (
            <Notice tone="warn">
              {plural(d.left_out.length, "tab")} you did not select (
              {d.left_out.join(", ")}) {d.left_out.length === 1 ? "is" : "are"} not in
              the download.
            </Notice>
          )}
          {d.nothing_found && (
            <Notice>
              Nothing was detected in the columns you chose, so no cell was
              changed. The workbook is still rebuilt from cell values, so you
              can download it below.
            </Notice>
          )}
          <DownloadCards
            safe={
              <>
                <DownloadButton
                  jobId={job.id}
                  kind="redacted"
                  label="Download redacted workbook"
                  tracker={flow.tracker}
                />
                <p className="text-muted">
                  Names are replaced with codes such as STF-10010, and changed
                  cells are yellow. Bank and payment details show as a mask such
                  as [ACCOUNT]. Tab names and column headers are checked too.
                </p>
                {d.formatting_note && (
                  <details>
                    <summary className="cursor-pointer text-muted">What is not carried over</summary>
                    <p className="mt-1 text-xs text-muted">{d.formatting_note}</p>
                  </details>
                )}
              </>
            }
            confidential={
              <CrosswalkCard jobId={job.id} hasMapping={d.has_mapping} tracker={flow.tracker} />
            }
          />
        </>
      )}
    </DownloadStep>
  );
}
