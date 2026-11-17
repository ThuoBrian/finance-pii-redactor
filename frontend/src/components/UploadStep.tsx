// Step 1: pick or drop one file. A good upload moves on to Options.
import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";

import { ACCEPTED_EXTENSIONS, api, isAccepted, type Job } from "../api";
import { Icon } from "./Icon";
import { Button, Notice, Spinner } from "./ui";

const UNSUPPORTED =
  "Unsupported file type. Please upload an Excel (.xlsx), PDF, or Word file. " +
  "An older .xls workbook can be re-saved as .xlsx from Excel.";

export function UploadStep({
  onUploaded,
  current,
  onContinue,
}: {
  onUploaded: (job: Job) => void;
  /** The file already uploaded, when the user came back to swap it. */
  current?: Job | null;
  onContinue?: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const upload = useMutation({ mutationFn: api.upload, onSuccess: onUploaded });

  const take = (file: File | undefined) => {
    if (!file) return;
    if (!isAccepted(file.name)) {
      setLocalError(UNSUPPORTED);
      return;
    }
    setLocalError(null);
    upload.mutate(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    take(e.dataTransfer.files[0]);
  };

  const error = localError ?? upload.error?.message;

  return (
    <section aria-labelledby="upload-heading" className="mx-auto max-w-xl">
      <h1 tabIndex={-1} id="upload-heading" className="text-3xl font-semibold tracking-tight">
        Upload a file
      </h1>
      <p className="mt-2 leading-relaxed text-muted">
        Excel, PDF or Word. Names become stable codes, and you check the result
        before you download.
      </p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-8 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center shadow-sm transition-colors duration-150 ${
          dragging ? "border-primary bg-primary-soft" : "border-border/50 bg-card hover:border-border"
        }`}
      >
        {upload.isPending ? (
          <Spinner label="Uploading..." />
        ) : (
          <>
            <span
              aria-hidden
              className={`flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-soft text-primary ring-8 ring-primary-soft/50 transition-transform duration-150 ${dragging ? "scale-110" : ""}`}
            >
              <Icon name="upload" className="h-6 w-6" />
            </span>
            <p className="mt-5 font-medium">
              {dragging ? "Drop to upload" : "Drag a file here"}
            </p>
            <p className="mt-1 text-sm text-muted">or</p>
            <Button variant="primary" className="mt-3" onClick={() => input.current?.click()}>
              Choose a file
            </Button>
            <ul aria-label="Accepted files" className="mt-6 flex flex-wrap justify-center gap-2 text-xs">
              {[".xlsx", ".pdf", ".docx"].map((ext) => (
                <li
                  key={ext}
                  className="rounded-md border border-border-soft bg-surface px-2 py-0.5 font-mono text-muted"
                >
                  {ext}
                </li>
              ))}
              <li className="px-1 py-0.5 text-muted">up to 200 MB</li>
            </ul>
          </>
        )}
        <input
          ref={input}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          aria-label="Choose a file to redact"
          tabIndex={-1}
          onChange={(e) => {
            take(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      {error && (
        <Notice tone="danger" className="mt-4">
          {error}
        </Notice>
      )}
      {current && onContinue && !upload.isPending && (
        <div className="mt-6 flex justify-end">
          <Button variant="primary" onClick={onContinue}>
            Continue with {current.filename}
          </Button>
        </div>
      )}
      <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-muted">
        <Icon name="lock" className="h-3.5 w-3.5" />
        The file is processed entirely on this computer.
      </p>
    </section>
  );
}
