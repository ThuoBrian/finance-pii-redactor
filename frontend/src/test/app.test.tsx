import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { api, ApiError, timeAgo } from "../api";

const MASTER_LIST = {
  total: 3,
  counts: { Staff: 2, Vendor: 1 },
  issues: [],
  path: "C:/made/up/Names List - Organized.xlsx",
  age_seconds: 7200,
  needs_setup: false,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === "/api/master-list") return json(MASTER_LIST);
    if (url === "/api/jobs/job1/excel/options") {
      return json({
        tabs: [{ name: "Jan", columns: ["Payee", "Amount"], default_columns: [0] }],
        summary: "1 tab (Jan) · 2 rows · text columns are picked for you",
        threshold: { default: 0.35, min: 0.1, max: 0.85, step: 0.05, help: "help" },
        entities: [{ code: "PERSON", label: "Person" }],
        entity_help: "kinds",
      });
    }
    if (url === "/api/jobs/job1/excel/estimate") return json({ warning: null });
    if (url === "/api/jobs" && init?.method === "POST") {
      return json({ id: "job1", filename: "budget.xlsx", format: "excel", size: 2048 }, 201);
    }
    return json({ detail: "not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the client header on every call", async () => {
    await api.masterList();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-FPR-Client"]).toBe("1");
  });

  it("surfaces the server's detail message", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "Too big" }, 413));
    await expect(api.masterList()).rejects.toEqual(new ApiError(413, "Too big"));
  });

  it("explains a server that is not running", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(api.masterList()).rejects.toThrow(/not responding/);
  });

  it("formats ages", () => {
    expect(timeAgo(30)).toBe("just now");
    expect(timeAgo(7200)).toBe("2 hours ago");
    expect(timeAgo(60)).toBe("just now");
    expect(timeAgo(120)).toBe("2 minutes ago");
    expect(timeAgo(86400)).toBe("1 day ago");
  });
});

describe("App shell", () => {
  it("shows the master-list count in the top bar", async () => {
    renderApp();
    expect(await screen.findByText("3 names")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload a file" })).toBeInTheDocument();
  });

  it("rejects an unsupported file without calling the server", async () => {
    renderApp();
    const input = screen.getByLabelText("Choose a file to redact");
    await userEvent.upload(input, new File(["x"], "old.xls"), { applyAccept: false });
    expect(await screen.findByRole("alert")).toHaveTextContent(/re-saved as .xlsx/);
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/jobs")).toBe(false);
  });

  it("moves to Options after an upload and shows the file", async () => {
    renderApp();
    const input = screen.getByLabelText("Choose a file to redact");
    await userEvent.upload(input, new File(["PK"], "budget.xlsx"));
    expect(await screen.findByRole("heading", { name: "Ready to redact" })).toBeInTheDocument();
    expect(await screen.findByText(/1 tab \(Jan\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Redact with recommended settings" })).toBeEnabled();
    expect(screen.getByText("budget.xlsx")).toBeInTheDocument();
    expect(screen.getByText("2 KB")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Change file" })).toBeInTheDocument(),
    );
  });

  it("offers master-list setup when no names loaded", async () => {
    fetchMock.mockImplementation(async () =>
      json({ ...MASTER_LIST, total: 0, counts: {}, needs_setup: true }),
    );
    renderApp();
    expect(
      await screen.findByRole("dialog", { name: "Set up your shared master list" }),
    ).toBeInTheDocument();
  });
});
