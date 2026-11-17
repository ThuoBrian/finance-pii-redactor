import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, formatBytes, type Job, type Prefs } from "./api";
import { AppMenu } from "./components/AppMenu";
import { DocxFlow } from "./components/docx/DocxFlow";
import { ExcelFlow } from "./components/excel/ExcelFlow";
import { PdfFlow } from "./components/pdf/PdfFlow";
import { MasterListPill } from "./components/MasterListPill";
import { SetupDialog } from "./components/SetupDialog";
import { Stepper, type StepIndex } from "./components/Stepper";
import { UploadStep } from "./components/UploadStep";
import { Icon } from "./components/Icon";
import { Badge, Button, Modal, Notice, ShieldMark } from "./components/ui";

const FORMAT_LABEL = { excel: "Excel", pdf: "PDF", docx: "Word" } as const;

/** While ``active``, closing or reloading the tab asks the browser's own
 * "leave this page?" question, since files not downloaded would be lost. */
export function useLeaveWarning(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
}

/** After each step change (not the first render), move focus to the new
 * step's heading so screen readers announce it. The heading may appear a
 * moment later, once its data loads, so this tries for about a second. */
export function useFocusHeading(step: number): void {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    let frame = 0;
    let tries = 0;
    const attempt = () => {
      const heading = document.querySelector<HTMLElement>("main h1");
      if (heading) heading.focus({ preventScroll: true });
      else if (++tries < 60) frame = requestAnimationFrame(attempt);
    };
    frame = requestAnimationFrame(attempt);
    return () => cancelAnimationFrame(frame);
  }, [step]);
}

/** "a", "a and b", "a, b and c". */
export function listing(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export default function App() {
  const [step, setStepState] = useState<StepIndex>(0);
  // Each step starts at the top of the page, like a new page would.
  const setStep = useCallback((next: StepIndex) => {
    setStepState(next);
    window.scrollTo?.({ top: 0 });
  }, []);
  const [job, setJob] = useState<Job | null>(null);
  const [setupDismissed, setSetupDismissed] = useState(false);
  const [closed, setClosed] = useState(false);
  // Words typed on Review carry over to the next file, until the app closes.
  const [words, setWords] = useState<string[]>([]);
  const [prefs, setPrefs] = useState<Prefs>({});
  // Expected files not yet downloaded for the current build (from the flow).
  const [pending, setPending] = useState<string[]>([]);
  const [confirmAnother, setConfirmAnother] = useState(false);
  const [setupRequested, setSetupRequested] = useState(false);
  const notDownloaded = listing(pending);

  useLeaveWarning(pending.length > 0);
  useFocusHeading(step);

  const masterList = useQuery({ queryKey: ["master-list"], queryFn: api.masterList });

  const startOver = useMutation({
    mutationFn: (id: string) => api.startOver(id),
    onSettled: () => {
      setJob(null);
      setPending([]);
      setStep(0);
    },
  });
  // "Redact another file": ask first when something would be lost.
  const finish = () => {
    if (pending.length) setConfirmAnother(true);
    else if (job) startOver.mutate(job.id);
  };
  const shutdown = useMutation({
    mutationFn: api.shutdown,
    onSuccess: () => setClosed(true),
  });

  if (closed) {
    return (
      <main className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md text-center">
          <ShieldMark className="mx-auto h-12 w-12" />
          <h1 className="mt-4 text-xl font-semibold">The app is closed</h1>
          <p className="mt-2 text-muted">You can close this browser tab now.</p>
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border-soft bg-card/80 backdrop-blur-md backdrop-saturate-150">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
          <ShieldMark />
          <span className="truncate text-[0.95rem] font-semibold tracking-tight">
            Finance PII Redactor
          </span>
          <span className="ml-auto hidden items-center gap-1.5 text-xs text-muted md:inline-flex">
            <Icon name="lock" className="h-3.5 w-3.5 text-success" />
            Everything stays on this computer
          </span>
          <div className="ml-auto flex items-center gap-1.5 md:ml-4">
            <MasterListPill
              data={masterList.data}
              isLoading={masterList.isLoading}
              error={masterList.error}
            />
            <AppMenu
              canStartOver={job !== null}
              onStartOver={() => job && startOver.mutate(job.id)}
              onClose={() => shutdown.mutate()}
              notDownloaded={notDownloaded}
            />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-16 pt-8">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <Stepper current={step} />
          {job && (
            <div className="card flex min-w-0 max-w-full items-center gap-2.5 rounded-full py-1.5 pl-2 pr-4 text-sm">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary">
                <Icon name={job.format === "excel" ? "sheet" : "file"} className="h-3.5 w-3.5" />
              </span>
              <Badge tone="info">{FORMAT_LABEL[job.format]}</Badge>
              <span className="min-w-0 max-w-56 truncate font-medium" title={job.filename}>
                {job.filename}
              </span>
              <span className="tabular shrink-0 text-muted">{formatBytes(job.size)}</span>
              {step > 1 && (
                <button
                  type="button"
                  className="ml-1 shrink-0 font-medium text-link underline-offset-2 hover:underline"
                  onClick={() => setStep(0)}
                >
                  Change
                </button>
              )}
            </div>
          )}
        </div>

        {shutdown.error && (
          <Notice tone="danger" className="mb-6">
            {shutdown.error.message}
          </Notice>
        )}

        {step === 0 && masterList.data && masterList.data.total === 0 && (
          <Notice tone="warn" className="mx-auto mb-6 max-w-xl">
            <p>
              <strong>No names loaded from the master list.</strong> Names are
              still found and replaced, but curated names won't get their
              team IDs.
            </p>
            <Button className="mt-3" onClick={() => setSetupRequested(true)}>
              Set up master list
            </Button>
          </Notice>
        )}
        {step === 0 && (
          <UploadStep
            current={job}
            onContinue={() => setStep(1)}
            onUploaded={(uploaded) => {
              setJob(uploaded);
              setStep(1);
            }}
          />
        )}
        {step > 0 && job?.format === "excel" && (
          <ExcelFlow
            key={job.id}
            job={job}
            step={step as 1 | 2 | 3}
            goTo={setStep}
            onFinish={finish}
            onPending={setPending}
            prefs={prefs.excel}
            onPrefs={(excel) => setPrefs((p) => ({ ...p, excel }))}
          />
        )}
        {step > 0 && job?.format === "docx" && (
          <DocxFlow
            key={job.id}
            job={job}
            step={step as 1 | 2 | 3}
            goTo={setStep}
            onFinish={finish}
            onPending={setPending}
            words={words}
            onWords={setWords}
            prefs={prefs.docx}
            onPrefs={(docx) => setPrefs((p) => ({ ...p, docx }))}
          />
        )}
        {step > 0 && job?.format === "pdf" && (
          <PdfFlow
            key={job.id}
            job={job}
            step={step as 1 | 2 | 3}
            goTo={setStep}
            onFinish={finish}
            onPending={setPending}
            words={words}
            onWords={setWords}
            prefs={prefs.pdf}
            onPrefs={(pdf) => setPrefs((p) => ({ ...p, pdf }))}
          />
        )}
      </main>

      <Modal
        open={confirmAnother}
        onOpenChange={setConfirmAnother}
        title="Redact another file?"
        description={`You haven't downloaded ${notDownloaded} yet; it will be lost.`}
      >
        <div className="flex justify-end gap-2">
          <Button onClick={() => setConfirmAnother(false)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => {
              setConfirmAnother(false);
              if (job) startOver.mutate(job.id);
            }}
          >
            Redact another file
          </Button>
        </div>
      </Modal>

      <SetupDialog
        open={
          setupRequested || (Boolean(masterList.data?.needs_setup) && !setupDismissed)
        }
        onDismiss={() => {
          setSetupDismissed(true);
          setSetupRequested(false);
        }}
        currentPath={masterList.data?.path ?? ""}
      />
    </div>
  );
}
