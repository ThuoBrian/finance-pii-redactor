// PDF: settings → Review → Download. Detection runs with fixed settings;
// false positives are unticked on Review. Stays mounted across the steps, so
// choices survive going Back.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  api,
  parseWords,
  plural,
  type Job,
  type PdfScanRequest,
  type Prefs,
} from "../../api";
import { Customize } from "../DetectionFields";
import { DownloadButton, DownloadCards, DownloadStep, crosswalkWarning } from "../DownloadCards";
import { InfoTip } from "../InfoTip";
import { Md } from "../Md";
import { OptionsFooter } from "../OptionsFooter";
import { ReviewLayout } from "../review/ReviewLayout";
import { TextOccurrenceTable } from "../review/Tables";
import { WordsBox, sameWords } from "../review/WordsBox";
import { ScanProgress } from "../TaskProgress";
import { Notice, Skeleton } from "../ui";
import { useFormatFlow } from "../useFormatFlow";
import { PdfMappingTable } from "./PdfMappingTable";
import { PdfPreview } from "./PdfPreview";

type Options = Omit<PdfScanRequest, "words">;
type ApplyArgs = { excluded: string[]; words: string[]; columns: string[] };

const RECOMMENDED: Options = { style: "pseudonymize", redact_images: true, read_scans: true };

const MAPPING_NOTE =
  "No names inside, only rows like [001] = 17728, so it is safe to keep with " +
  "the PDF. Keep it: without it the labels cannot be decoded. Decoding also " +
  "needs the master list, which stays access-controlled.";

function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

export function PdfFlow({
  job,
  step,
  goTo,
  onFinish,
  words,
  onWords,
  prefs,
  onPrefs,
  onPending,
}: {
  job: Job;
  step: 1 | 2 | 3;
  goTo: (step: 0 | 1 | 2 | 3) => void;
  onFinish: () => void;
  words: string[];
  onWords: (words: string[]) => void;
  prefs?: Prefs["pdf"];
  onPrefs: (prefs: Prefs["pdf"]) => void;
  /** Labels of expected files not yet downloaded for this build. */
  onPending: (missing: string[]) => void;
}) {
  const queryClient = useQueryClient();
  const options = useQuery({
    queryKey: ["pdf-options", job.id],
    queryFn: () => api.pdf.options(job.id),
  });
  const [choices, setChoicesState] = useState<Options>(prefs ?? RECOMMENDED);
  const setChoices = (next: Options) => {
    setChoicesState(next);
    onPrefs(next);
  };
  const [wordsText, setWordsText] = useState(words.join("\n"));
  const [columns, setColumns] = useState<string[]>([]);
  const flow = useFormatFlow(job.id, step, goTo, onPending, {
    name: "pdf",
    scan: (body: Options) => api.pdf.scan(job.id, { ...body, words: parseWords(wordsText) }),
    review: () => api.pdf.review(job.id),
    apply: (a: ApplyArgs) => api.pdf.apply(job.id, a.excluded, a.words, a.columns),
    download: () => api.pdf.download(job.id),
    expected: (r) => [
      { kind: "redacted", label: "the redacted PDF" },
      ...(!r.blackout && r.mapping.length
        ? [{ kind: "pdf-mapping", label: "the label mapping" }]
        : []),
    ],
  });
  const namesFile = useMutation({
    mutationFn: (enabled: boolean) => api.pdf.namesFile(job.id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pdf-download", job.id] }),
  });

  // A new result resets the boxes to what it was built with; the words are
  // remembered for the next file in this session.
  const result = flow.review.data;
  useEffect(() => {
    if (!result) return;
    setWordsText(result.words.join("\n"));
    setColumns(result.columns);
    onWords(result.words);
  }, [result]); // eslint-disable-line react-hooks/exhaustive-deps

  if (step === 1) {
    if (options.error) return <Notice tone="danger">{options.error.message}</Notice>;
    const o = options.data;
    if (!o) return <Skeleton label="Reading the PDF..." />;
    if (flow.scanning) {
      return <ScanProgress jobId={job.id} unit="page" progress={flow.progress} />;
    }
    const sizeNote =
      choices.read_scans && o.can_read_scans ? o.size_note_reading : o.size_note_not_reading;
    return (
      <section aria-labelledby="options-heading" className="mx-auto max-w-2xl">
        <h1 tabIndex={-1} id="options-heading" className="text-3xl font-semibold tracking-tight">
          Ready to redact
        </h1>
        <p className="mt-2 leading-relaxed text-muted">
          {o.total_pages > 0 && `${plural(o.total_pages, "page")}. `}
          Names, organizations, emails, websites, bank details and addresses are
          found automatically. Images are blacked out. Missed a name? You can add
          it on the next step.
        </p>
        <Customize hint="labels or black boxes, images, scanned pages">
          <fieldset>
            <legend className="text-sm font-medium">Redaction style</legend>
            <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              {(
                [
                  ["pseudonymize", "Replace with labels such as [001]", "A separate mapping file says which Internal ID each label stands for."],
                  ["blackout", "Black out (cover with black boxes)", "Covers matched text with a black box, with nothing to decode."],
                ] as const
              ).map(([value, label, help]) => (
                <label
                  key={value}
                  className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border-soft bg-card p-3 shadow-sm transition hover:bg-surface has-[:checked]:border-primary/60 has-[:checked]:bg-primary-soft"
                >
                  <input
                    type="radio"
                    name="pdf-style"
                    className="mt-0.5"
                    checked={choices.style === value}
                    onChange={() => setChoices({ ...choices, style: value })}
                  />
                  <span>
                    <span className="font-medium">{label}</span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">{help}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex items-center text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={choices.redact_images}
                onChange={(e) => setChoices({ ...choices, redact_images: e.target.checked })}
              />
              Also black out images and logos
            </label>
            <InfoTip label="Black out images">
              Covers every embedded image on each page. A logo drawn as vector
              art (lines and shapes, not a picture) won't be caught.
            </InfoTip>
          </div>
          <div className="text-sm">
            <div className="flex items-center">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!o.can_read_scans}
                  checked={choices.read_scans && o.can_read_scans}
                  onChange={(e) => setChoices({ ...choices, read_scans: e.target.checked })}
                />
                Read the text on scanned pages (OCR)
              </label>
              <InfoTip label="Reading scanned pages">
                Printed text on a scanned page is read and its names redacted.
                Anything not read with confidence (signatures, handwriting,
                stamps) is blacked out when images are. Several seconds a page.
              </InfoTip>
            </div>
            {!o.can_read_scans && (
              <p className="ml-6 text-xs text-muted">
                OCR is not installed on this computer; re-run the installer.
              </p>
            )}
          </div>
        </Customize>
        {sizeNote && (
          <Notice tone="warn" className="mt-4">
            <Md text={sizeNote} />
          </Notice>
        )}
        <OptionsFooter
          recommended={
            choices.style === RECOMMENDED.style &&
            choices.redact_images === RECOMMENDED.redact_images &&
            choices.read_scans === RECOMMENDED.read_scans
          }
          busy={flow.scan.isPending}
          notice={flow.scanNotice}
          error={flow.scanError}
          onBack={() => goTo(0)}
          onScan={() => flow.scan.mutate(choices)}
        />
      </section>
    );
  }

  if (flow.review.error) return <Notice tone="danger">{flow.review.error.message}</Notice>;
  const r = result;
  if (!r) return <Skeleton label="Loading..." />;

  if (step === 2) {
    const columnsPending = !sameSet(columns, r.columns);
    const wordsPending = !sameWords(parseWords(wordsText), r.words);
    const firstPage = r.occurrences[0]?.location ?? 1;
    return (
      <>
        {(r.scanned_note || r.not_located) && (
          <div className="mb-4 space-y-3">
            {r.scanned_note && (
              <Notice tone="warn">
                <Md text={r.scanned_note} />
              </Notice>
            )}
            {r.not_located && (
              <Notice tone="danger">
                <Md text={r.not_located} />
              </Notice>
            )}
          </div>
        )}
        <ReviewLayout
          heading="Review what was found"
          summary={r.summary}
          rows={r.rows}
          filters={r.filters}
          clean={r.clean}
          applied={r.applied}
          carried={r.carried}
          applying={flow.apply.isPending}
          applyError={flow.apply.error?.message ?? null}
          onApply={(excluded) =>
            flow.apply.mutate({ excluded, words: r.words, columns: r.columns })
          }
          onBack={() => goTo(1)}
          onContinue={() => goTo(3)}
          hold={columnsPending || wordsPending ? "additions not applied yet" : null}
          additions={
            <div className="space-y-5">
              {r.table_columns.length > 0 && (
                <fieldset>
                  <legend className="inline-flex items-center text-sm font-medium">
                    Table columns to redact in full
                    <InfoTip label="Table columns">
                      Every entry in a chosen column is replaced, and the same
                      value anywhere else on that page too. Columns that look
                      like names, accounts or contact details start chosen. The
                      header row stays.
                    </InfoTip>
                  </legend>
                  <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
                    {r.table_columns.map((c) => (
                      <label key={c.key} className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-surface">
                        <input
                          type="checkbox"
                          checked={columns.includes(c.key)}
                          onChange={() =>
                            setColumns((cur) =>
                              cur.includes(c.key) ? cur.filter((k) => k !== c.key) : [...cur, c.key],
                            )
                          }
                        />
                        {c.header}
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}
              <WordsBox
                text={wordsText}
                onTextChange={setWordsText}
                applied={r.words}
                busy={flow.apply.isPending}
                warnLabelShaped
                otherChanges={columnsPending}
                onAdd={(w) => flow.apply.mutate({ excluded: r.applied, words: w, columns })}
              />
            </div>
          }
          occurrences={r.occurrences}
          focusPanel="preview"
          panels={(selection) => {
            const occurrence = selection
              ? r.occurrences.filter((o) => o.key === selection.key)[selection.place]
              : undefined;
            return [
              {
                id: "preview",
                label: "Preview",
                content: (
                  <PdfPreview
                    jobId={job.id}
                    pageCount={r.page_count}
                    version={flow.version}
                    initialPage={firstPage}
                    focus={
                      selection && occurrence
                        ? { page: occurrence.location, seq: selection.seq }
                        : null
                    }
                  />
                ),
              },
              {
                id: "mapping",
                label: r.blackout ? "Mapping" : `Mapping (${r.mapping.length})`,
                content: <PdfMappingTable rows={r.mapping} blackout={r.blackout} />,
              },
              {
                id: "where",
                label: "Where found",
                content: (
                  <TextOccurrenceTable
                    rows={r.occurrences}
                    locationLabel="Page"
                    onlyKey={selection?.key ?? null}
                  />
                ),
              },
            ];
          }}
        />
      </>
    );
  }

  return (
    <DownloadStep info={flow.info} onBack={() => goTo(2)} onFinish={onFinish}>
      {(d) => (
        <>
          {d.before_share.length > 0 && (
            <Notice tone={d.before_share_warn ? "warn" : "info"}>
              <p className="font-semibold">Before you share this PDF</p>
              {d.before_share.map((note, i) => (
                <div key={i} className="mt-2">
                  <Md text={note} />
                </div>
              ))}
            </Notice>
          )}
          {d.not_located && (
            <Notice tone="danger">
              <Md text={d.not_located} />
            </Notice>
          )}
          <DownloadCards
            safe={
              <>
                <DownloadButton
                  jobId={job.id}
                  kind="redacted"
                  label={d.blackout ? "Download blacked-out PDF" : "Download redacted PDF"}
                  tracker={flow.tracker}
                />
                <p className="text-muted">
                  {d.blackout
                    ? "Matched text and images are covered with black boxes."
                    : "Names become labels such as [001]; bank details and addresses become masks such as [ACCOUNT]."}
                  {d.removed_links > 0 &&
                    ` ${plural(d.removed_links, "link target")} removed, link text kept.`}
                </p>
                {!d.blackout && d.has_mapping && (
                  <div className="border-t border-border-soft pt-3">
                    <DownloadButton
                      jobId={job.id}
                      kind="pdf-mapping"
                      label="Download label mapping (CSV, no names)"
                      tracker={flow.tracker}
                      variant="secondary"
                    />
                    <p className="mt-2 text-xs text-muted">
                      {MAPPING_NOTE}
                      {d.bracketed > 0 &&
                        ` This PDF already had ${plural(d.bracketed, "bracketed number")} of its own (such as footnote markers) that look like the [001] labels; the mapping names every label this tool added.`}
                    </p>
                  </div>
                )}
              </>
            }
            confidential={
              d.blackout || !d.has_mapping ? (
                <p className="text-muted">
                  {d.blackout
                    ? "Black out leaves nothing to decode, so there is no file here."
                    : "Nothing was replaced with a label, so there is no mapping."}
                </p>
              ) : (
                <>
                  <label className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={d.names_file}
                      disabled={namesFile.isPending}
                      onChange={(e) => namesFile.mutate(e.target.checked)}
                    />
                    <span>
                      Also prepare a mapping with names
                      <span className="block text-xs text-muted">
                        For reading the mapping without the master list. The label
                        mapping stays names-free.
                      </span>
                    </span>
                  </label>
                  {d.names_file ? (
                    <>
                      <DownloadButton
                        jobId={job.id}
                        kind="pdf-names"
                        label="Download name mapping (CSV)"
                        tracker={flow.tracker}
                        variant="secondary"
                      />
                      <p className="text-muted">{crosswalkWarning("labels", "redacted PDF")}</p>
                    </>
                  ) : (
                    <p className="text-xs text-muted">
                      Not needed in most cases: the label mapping and the master
                      list decode every label.
                    </p>
                  )}
                  {namesFile.error && <Notice tone="danger">{namesFile.error.message}</Notice>}
                </>
              )
            }
          />
        </>
      )}
    </DownloadStep>
  );
}
