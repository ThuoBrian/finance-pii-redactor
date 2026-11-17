// Client for the local API. Every call carries X-FPR-Client: the server
// refuses /api requests without it, which stops other web pages the user has
// open from calling this app (see finance_redactor/presentation/security.py).

export type QualityIssue = {
  severity: "warning" | "info" | string;
  title: string;
  detail: string;
  examples: string[];
  total: number;
};

export type MasterList = {
  total: number;
  counts: Record<string, number>;
  issues: QualityIssue[];
  path: string;
  age_seconds: number | null;
  needs_setup: boolean;
};

export type FileFormat = "excel" | "pdf" | "docx";

export type Job = {
  id: string;
  filename: string;
  format: FileFormat;
  size: number;
};

export type Task = {
  status: "idle" | "running" | "done" | "error" | "cancelled";
  label: string;
  done: number;
  total: number;
  error: string;
};

export type JobStatus = Job & { task: Task };

export type ReviewRow = {
  key: string;
  term: string;
  why: string;
  kind: string;
  source: string;
  confidence: number;
  hint: string;
  occurrences: number;
};

export type SourceFilter = { label: string; source: string; count: number };

export type MappingRow = {
  original_name: string;
  kind: string;
  pseudonym: string;
  flagged: boolean;
  possible_match: string;
};

export type ExcelTab = {
  name: string;
  columns: string[];
  default_columns: number[];
};

export type ExcelOptions = {
  tabs: ExcelTab[];
  summary: string;
  threshold: { default: number; min: number; max: number; step: number; help: string };
  entities: { code: string; label: string }[];
  entity_help: string;
};

export type ExcelSelection = { tabs: string[]; columns: Record<string, number[]> };
export type ExcelScanRequest = ExcelSelection & { entities: string[]; threshold: number };

export type Occurrence = {
  sheet: string;
  /** 1-based data row; null for a tab name or header. */
  row: number | null;
  column: string;
  place: "cell" | "header" | "tab";
  /** The original column header ("" for a tab name). */
  column_name: string;
  key: string;
  term: string;
};

export type ExcelReview = {
  summary: string;
  entity_count: number;
  cell_count: number;
  rows: ReviewRow[];
  applied: string[];
  carried: string[];
  filters: SourceFilter[];
  clean: boolean;
  mapping: MappingRow[];
  occurrences: Occurrence[];
  tabs: string[];
};

export type ExcelPreview = {
  tab: number;
  tabs: string[];
  total_rows: number;
  start: number;
  page_size: number;
  columns: string[];
  original_columns: string[];
  rows: string[][];
  original_rows: string[][];
  marked: [number, number][];
  elsewhere: number;
};

export type ExcelDownloadInfo = {
  excluded: string[];
  left_out: string[];
  nothing_found: boolean;
  formatting_note: string;
  has_mapping: boolean;
};

export type TextOccurrence = {
  location: number;
  key: string;
  term: string;
  kind: string;
};

export type DetectionOptions = {
  threshold: ExcelOptions["threshold"];
  entities: ExcelOptions["entities"];
  entity_help: string;
};

export type DetectionChoices = { entities: string[]; threshold: number };

export type DocxReview = {
  summary: string;
  rows: ReviewRow[];
  applied: string[];
  carried: string[];
  words: string[];
  filters: SourceFilter[];
  clean: boolean;
  mapping: MappingRow[];
  occurrences: TextOccurrence[];
};

export type DocxDownloadInfo = {
  excluded: string[];
  removed_links: number;
  has_mapping: boolean;
};

export type PdfOptions = {
  can_read_scans: boolean;
  total_pages: number;
  size_note_reading: string;
  size_note_not_reading: string;
};

export type PdfStyle = "pseudonymize" | "blackout";

export type PdfScanRequest = {
  style: PdfStyle;
  redact_images: boolean;
  read_scans: boolean;
  words: string[];
};

export type PdfMappingRow = {
  label: string;
  original_name: string;
  kind: string;
  internal_id: string;
  flagged: string;
  possible_match: string;
};

export type PdfReview = {
  summary: string;
  page_count: number;
  blackout: boolean;
  scanned_note: string;
  not_located: string;
  rows: ReviewRow[];
  applied: string[];
  carried: string[];
  words: string[];
  table_columns: { key: string; header: string }[];
  columns: string[];
  filters: SourceFilter[];
  clean: boolean;
  mapping: PdfMappingRow[];
  occurrences: TextOccurrence[];
};

export type PdfDownloadInfo = {
  excluded: string[];
  blackout: boolean;
  removed_links: number;
  before_share: string[];
  before_share_warn: boolean;
  not_located: string;
  has_mapping: boolean;
  bracketed: number;
  names_file: boolean;
};

/** Customize choices remembered for the session, per format. Excel tab and
 * column choices belong to one workbook, so they are not remembered. */
export type Prefs = {
  excel?: DetectionChoices;
  docx?: DetectionChoices;
  pdf?: Omit<PdfScanRequest, "words">;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const CLIENT_HEADER = { "X-FPR-Client": "1" };

/**
 * Fetch with the client header; a failure becomes an ``ApiError`` carrying the
 * server's ``detail`` message when it sent one.
 */
async function fetchOk(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { ...CLIENT_HEADER, ...init.headers },
    });
  } catch {
    throw new ApiError(0, "The app is not responding. Is its window still open?");
  }
  if (!response.ok) {
    let message = response.statusText || `Request failed (${response.status})`;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        const detail = (body as { detail: unknown }).detail;
        if (typeof detail === "string") message = detail;
      }
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(response.status, message);
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetchOk(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const api = {
  masterList: () => request<MasterList>("/api/master-list"),
  refreshMasterList: () => postJson<MasterList>("/api/master-list/refresh"),
  checkFolder: (folder: string) =>
    postJson<{ found: boolean }>("/api/master-list/check", { folder }),
  saveFolder: (folder: string, saveAnyway: boolean) =>
    postJson<MasterList>("/api/master-list/setup", {
      folder,
      save_anyway: saveAnyway,
    }),
  skipSetup: () => postJson<MasterList>("/api/master-list/skip"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Job>("/api/jobs", { method: "POST", body: form });
  },
  startOver: (jobId: string) => request<void>(jobPath(jobId), { method: "DELETE" }),
  shutdown: () => postJson<{ status: string }>("/api/shutdown"),
  jobStatus: (jobId: string) => request<JobStatus>(jobPath(jobId)),
  cancelJob: (jobId: string) =>
    postJson<{ cancelling: boolean }>(`${jobPath(jobId)}/cancel`),
  excel: {
    options: (jobId: string) =>
      request<ExcelOptions>(`${jobPath(jobId)}/excel/options`),
    estimate: (jobId: string, selection: ExcelSelection) =>
      postJson<{ warning: string | null }>(`${jobPath(jobId)}/excel/estimate`, selection),
    scan: (jobId: string, body: ExcelScanRequest) =>
      postJson<{ status: string }>(`${jobPath(jobId)}/excel/scan`, body),
    review: (jobId: string) => request<ExcelReview>(`${jobPath(jobId)}/excel/review`),
    apply: (jobId: string, excluded: string[]) =>
      postJson<ExcelReview>(`${jobPath(jobId)}/excel/apply`, { excluded }),
    preview: (jobId: string, tab: number, start: number) =>
      request<ExcelPreview>(
        `${jobPath(jobId)}/excel/preview?tab=${tab}&start=${start}`,
      ),
    download: (jobId: string) =>
      request<ExcelDownloadInfo>(`${jobPath(jobId)}/excel/download`),
  },
  docx: {
    options: (jobId: string) =>
      request<DetectionOptions>(`${jobPath(jobId)}/docx/options`),
    scan: (jobId: string, body: DetectionChoices & { words: string[] }) =>
      postJson<{ status: string }>(`${jobPath(jobId)}/docx/scan`, body),
    review: (jobId: string) => request<DocxReview>(`${jobPath(jobId)}/docx/review`),
    apply: (jobId: string, excluded: string[], words: string[]) =>
      postJson<DocxReview>(`${jobPath(jobId)}/docx/apply`, { excluded, words }),
    download: (jobId: string) =>
      request<DocxDownloadInfo>(`${jobPath(jobId)}/docx/download`),
  },
  pdf: {
    options: (jobId: string) => request<PdfOptions>(`${jobPath(jobId)}/pdf/options`),
    scan: (jobId: string, body: PdfScanRequest) =>
      postJson<{ status: string }>(`${jobPath(jobId)}/pdf/scan`, body),
    review: (jobId: string) => request<PdfReview>(`${jobPath(jobId)}/pdf/review`),
    apply: (jobId: string, excluded: string[], words: string[], columns: string[]) =>
      postJson<PdfReview>(`${jobPath(jobId)}/pdf/apply`, { excluded, words, columns }),
    download: (jobId: string) =>
      request<PdfDownloadInfo>(`${jobPath(jobId)}/pdf/download`),
    namesFile: (jobId: string, enabled: boolean) =>
      postJson<{ enabled: boolean }>(`${jobPath(jobId)}/pdf/names-file`, { enabled }),
    /** A page as an object URL; the caller revokes it. */
    page: async (jobId: string, n: number, version: "redacted" | "original") => {
      const response = await fetchOk(`${jobPath(jobId)}/pdf/page?n=${n}&version=${version}`);
      return URL.createObjectURL(await response.blob());
    },
  },
};

/** The non-blank lines of a text box, trimmed, in order. */
export function parseWords(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((w) => w.trim())
    .filter(Boolean);
}

function jobPath(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}`;
}

/**
 * Fetch an output file and hand it to the browser as a download.
 *
 * Through fetch rather than a plain link so the request carries the client
 * header; the file name comes from the server (never the upload's own name).
 */
export async function downloadFile(jobId: string, kind: string): Promise<void> {
  const response = await fetchOk(`${jobPath(jobId)}/files/${encodeURIComponent(kind)}`);
  const match = /filename="([^"]+)"/.exec(
    response.headers.get("Content-Disposition") ?? "",
  );
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Give the browser a moment to start the download before freeing it.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function plural(count: number, singular: string, pluralForm?: string): string {
  return `${count.toLocaleString()} ${count === 1 ? singular : (pluralForm ?? `${singular}s`)}`;
}

export const ACCEPTED_EXTENSIONS = [".xlsx", ".pdf", ".docx"] as const;

export function isAccepted(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** A rough, plain age such as "just now" or "3 hours ago". */
export function timeAgo(seconds: number): string {
  if (seconds < 90) return "just now";
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ] as const) {
    if (seconds >= size) {
      const n = Math.floor(seconds / size);
      return `${n} ${unit}${n === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}
