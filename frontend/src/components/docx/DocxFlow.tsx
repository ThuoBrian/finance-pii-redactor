// Word: settings → Review → Download. Pseudonymize only: Word text stays
// editable, as with Excel. Stays mounted across the three steps, so choices
// survive going Back.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  api,
  parseWords,
  plural,
  type DetectionChoices,
  type Job,
  type Prefs,
} from "../../api";
import { Customize, DetectionFields } from "../DetectionFields";
import { CrosswalkCard, DownloadButton, DownloadCards, DownloadStep } from "../DownloadCards";
import { OptionsFooter } from "../OptionsFooter";
import { MappingTable, TextOccurrenceTable } from "../review/Tables";
import { ReviewLayout } from "../review/ReviewLayout";
import { WordsBox, sameWords } from "../review/WordsBox";
import { ScanProgress } from "../TaskProgress";
import { Notice, Skeleton } from "../ui";
import { useFormatFlow } from "../useFormatFlow";

export function DocxFlow({
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
  /** Words typed for an earlier file in this session; used on the first build. */
  words: string[];
  onWords: (words: string[]) => void;
  prefs?: Prefs["docx"];
  onPrefs: (prefs: Prefs["docx"]) => void;
  /** Labels of expected files not yet downloaded for this build. */
  onPending: (missing: string[]) => void;
}) {
  const options = useQuery({
    queryKey: ["docx-options", job.id],
    queryFn: () => api.docx.options(job.id),
  });
  const [choices, setChoices] = useState<DetectionChoices | null>(null);
  const [wordsText, setWordsText] = useState(words.join("\n"));
  const flow = useFormatFlow(job.id, step, goTo, onPending, {
    name: "docx",
    scan: (body: DetectionChoices) =>
      api.docx.scan(job.id, { ...body, words: parseWords(wordsText) }),
    review: () => api.docx.review(job.id),
    apply: (a: { excluded: string[]; words: string[] }) =>
      api.docx.apply(job.id, a.excluded, a.words),
    download: () => api.docx.download(job.id),
    expected: (r) => [
      { kind: "redacted", label: "the redacted document" },
      ...(r.mapping.length ? [{ kind: "crosswalk", label: "the name mapping" }] : []),
    ],
  });

  useEffect(() => {
    if (!options.data || choices) return;
    const known = options.data.entities.map((e) => e.code);
    setChoices(
      prefs
        ? { threshold: prefs.threshold, entities: prefs.entities.filter((e) => known.includes(e)) }
        : { entities: known, threshold: options.data.threshold.default },
    );
  }, [options.data, choices]); // eslint-disable-line react-hooks/exhaustive-deps

  // A new result resets the box to the words it was built with, and they are
  // remembered for the next file in this session.
  const appliedWords = flow.review.data?.words;
  useEffect(() => {
    if (!appliedWords) return;
    setWordsText(appliedWords.join("\n"));
    onWords(appliedWords);
  }, [appliedWords]); // eslint-disable-line react-hooks/exhaustive-deps

  if (step === 1) {
    if (options.error) return <Notice tone="danger">{options.error.message}</Notice>;
    if (!options.data || !choices) return <Skeleton label="Loading..." />;
    if (flow.scanning) {
      return <ScanProgress jobId={job.id} unit="paragraph" progress={flow.progress} />;
    }
    return (
      <section aria-labelledby="options-heading" className="mx-auto max-w-2xl">
        <h1 tabIndex={-1} id="options-heading" className="text-3xl font-semibold tracking-tight">
          Ready to redact
        </h1>
        <p className="mt-2 leading-relaxed text-muted">
          Names, organizations, emails, websites, bank details and addresses are
          found automatically. Missed a name? You can add it on the next step.
        </p>
        <Customize hint="kinds of information, confidence">
          <DetectionFields
            options={options.data}
            choices={choices}
            onChange={(next) => {
              setChoices(next);
              onPrefs(next);
            }}
          />
        </Customize>
        {!choices.entities.length && (
          <Notice tone="warn" className="mt-4">
            Choose at least one kind of information to hide, under Customize.
          </Notice>
        )}
        <OptionsFooter
          recommended={
            choices.threshold === options.data.threshold.default &&
            choices.entities.length === options.data.entities.length
          }
          busy={flow.scan.isPending}
          disabled={!choices.entities.length}
          notice={flow.scanNotice}
          error={flow.scanError}
          onBack={() => goTo(0)}
          onScan={() => flow.scan.mutate(choices)}
        />
      </section>
    );
  }

  if (flow.review.error) return <Notice tone="danger">{flow.review.error.message}</Notice>;
  const r = flow.review.data;
  if (!r) return <Skeleton label="Loading..." />;

  if (step === 2) {
    const wordsPending = !sameWords(parseWords(wordsText), r.words);
    return (
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
        onApply={(excluded) => flow.apply.mutate({ excluded, words: r.words })}
        onBack={() => goTo(1)}
        onContinue={() => goTo(3)}
        hold={wordsPending ? "typed words not added yet" : null}
        additions={
          <WordsBox
            text={wordsText}
            onTextChange={setWordsText}
            applied={r.words}
            busy={flow.apply.isPending}
            onAdd={(w) => flow.apply.mutate({ excluded: r.applied, words: w })}
          />
        }
        occurrences={r.occurrences}
        focusPanel="where"
        panels={(selection) => [
          {
            id: "mapping",
            label: `Mapping (${r.mapping.length})`,
            content: <MappingTable rows={r.mapping} />,
          },
          {
            id: "where",
            label: "Where found",
            content: (
              <TextOccurrenceTable
                rows={r.occurrences}
                locationLabel="Paragraph"
                onlyKey={selection?.key ?? null}
              />
            ),
          },
        ]}
      />
    );
  }

  return (
    <DownloadStep info={flow.info} onBack={() => goTo(2)} onFinish={onFinish}>
      {(d) => (
        <DownloadCards
          safe={
            <>
              <DownloadButton
                jobId={job.id}
                kind="redacted"
                label="Download redacted Word document"
                tracker={flow.tracker}
              />
              <p className="text-muted">
                Names are replaced with codes such as STF-10010. Bank and
                payment details and addresses show as a mask such as
                [ACCOUNT].
                {d.removed_links > 0 &&
                  ` ${plural(d.removed_links, "hyperlink target")} removed; the link text stays, redacted where it matched.`}
              </p>
            </>
          }
          confidential={
            <CrosswalkCard jobId={job.id} hasMapping={d.has_mapping} tracker={flow.tracker} />
          }
        />
      )}
    </DownloadStep>
  );
}
