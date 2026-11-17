import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { api, type MappingRow, type Task } from "../api";
import { InfoTip } from "../components/InfoTip";
import { MappingTable } from "../components/review/Tables";
import { TaskProgress, timeLeft } from "../components/TaskProgress";
import { Toast, TOAST_MS } from "../components/Toast";

function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function job(task: Partial<Task>) {
  return {
    id: "j",
    filename: "made-up.pdf",
    format: "pdf" as const,
    size: 10,
    task: { status: "running" as const, label: "Scanning", done: 0, total: 0, error: "", ...task },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("time left", () => {
  it("stays quiet until the estimate means something", () => {
    expect(timeLeft(0, 100, 5_000)).toBeNull(); // nothing done yet
    expect(timeLeft(2, 100, 5_000)).toBeNull(); // under 5%
    expect(timeLeft(50, 100, 5_000)).toBeNull(); // a 10-second run
  });

  it("estimates from the pace so far", () => {
    expect(timeLeft(10, 100, 60_000)).toBe("about 9 minutes left");
    expect(timeLeft(90, 100, 120_000)).toBe("less than a minute left");
    // Progress already made before timing started is not counted.
    expect(timeLeft(20, 100, 60_000, 10)).toBe("about 8 minutes left");
  });
});

describe("cancelling a scan", () => {
  it("asks the server to stop, then reports the cancellation", async () => {
    const status = vi
      .spyOn(api, "jobStatus")
      .mockResolvedValueOnce(job({ done: 3, total: 40 }))
      .mockResolvedValue(job({ status: "cancelled", done: 3, total: 40 }));
    const cancel = vi.spyOn(api, "cancelJob").mockResolvedValue({ cancelling: true });
    const onCancelled = vi.fn();
    withQuery(
      <TaskProgress jobId="j" unit="page" onDone={vi.fn()} onError={vi.fn()} onCancelled={onCancelled} />,
    );
    expect(await screen.findByText(/3 of 40 pages checked/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(cancel).toHaveBeenCalledWith("j");
    await waitFor(() => expect(onCancelled).toHaveBeenCalled(), { timeout: 2000 });
    expect(status).toHaveBeenCalledTimes(2);
  });
});

describe("tables", () => {
  const rows: MappingRow[] = Array.from({ length: 13 }, (_, i) => ({
    original_name: `Person ${String.fromCharCode(77 - i)}`,
    kind: "Person",
    pseudonym: `STF-${100 + i}`,
    flagged: false,
    possible_match: "",
  }));

  it("long tables search, and headers sort", async () => {
    render(<MappingTable rows={rows} />);
    const table = screen.getByRole("table");
    const names = () =>
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((r) => r.firstElementChild?.textContent);
    expect(names()[0]).toBe("Person M");
    await userEvent.click(within(table).getByRole("button", { name: /Original name/ }));
    expect(names()[0]).toBe("Person A");
    await userEvent.click(within(table).getByRole("button", { name: /Original name/ }));
    expect(names()[0]).toBe("Person M");
    await userEvent.type(screen.getByRole("searchbox", { name: "Find a name or code" }), "STF-105");
    expect(names()).toEqual(["Person H"]);
  });

  it("short tables have no search box", () => {
    render(<MappingTable rows={rows.slice(0, 3)} />);
    expect(screen.queryByRole("searchbox")).toBeNull();
  });
});

describe("small pieces", () => {
  it("a toast clears itself", () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    render(<Toast onClose={onClose}>Rebuilt the file.</Toast>);
    expect(screen.getByRole("status")).toHaveTextContent("Rebuilt the file.");
    act(() => vi.advanceTimersByTime(TOAST_MS));
    expect(onClose).toHaveBeenCalled();
  });

  it("an info tip opens on click", async () => {
    render(<InfoTip label="Confidence threshold">Lower catches more.</InfoTip>);
    expect(screen.queryByText("Lower catches more.")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "About Confidence threshold" }));
    expect(screen.getByText("Lower catches more.")).toBeInTheDocument();
  });
});

describe("focus follows the step", () => {
  it("moves to the new step's heading after an upload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const json = (body: unknown, status = 200) =>
          new Response(JSON.stringify(body), {
            status,
            headers: { "Content-Type": "application/json" },
          });
        if (url === "/api/master-list") {
          return json({ total: 2, counts: { Staff: 2 }, issues: [], path: "x", age_seconds: null, needs_setup: false });
        }
        if (url === "/api/jobs" && init?.method === "POST") {
          return json({ id: "job1", filename: "letter.docx", format: "docx", size: 10 }, 201);
        }
        if (url === "/api/jobs/job1/docx/options") {
          return json({
            threshold: { default: 0.35, min: 0.1, max: 0.85, step: 0.05, help: "help" },
            entities: [{ code: "PERSON", label: "Person" }],
            entity_help: "kinds",
          });
        }
        return json({ detail: "not found" }, 404);
      }),
    );
    withQuery(<App />);
    await userEvent.upload(screen.getByLabelText("Choose a file to redact"), new File(["PK"], "letter.docx"));
    const heading = await screen.findByRole("heading", { name: "Ready to redact" });
    await waitFor(() => expect(heading).toHaveFocus());
  });
});
