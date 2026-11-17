// Step 1: pick or drop one file. A good upload moves on to Options.
import { useMutation } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";

import { ACCEPTED_EXTENSIONS, api, isAccepted, type Job } from "../api";
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
      <h1 tabIndex={-1} id="upload-heading" className="text-2xl font-semibold tracking-tight">
        Upload a file
      </h1>
      <p className="mt-1 text-muted">
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
        className={`mt-6 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors ${
          dragging ? "border-primary bg-surface" : "border-border bg-bg"
        }`}
      >
        {upload.isPending ? (
          <Spinner label="Uploading..." />
        ) : (
          <>
            <p className="text-sm text-muted">Drag a file here, or</p>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="mt-3 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover"
            >
              Choose a file
            </button>
            <p className="mt-3 text-xs text-muted">.xlsx, .pdf or .docx · up to 200 MB</p>
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
      <p className="mt-6 text-center text-xs text-muted">
        The file is processed entirely on this computer.
      </p>
    </section>
  );
}
