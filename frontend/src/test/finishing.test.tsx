import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App, { listing, useLeaveWarning } from "../App";
import { useDownloadTracker } from "../components/DownloadCards";

const FILES = [
  { kind: "redacted", label: "the redacted PDF" },
  { kind: "pdf-mapping", label: "the label mapping" },
];

afterEach(() => vi.unstubAllGlobals());

describe("download tracking", () => {
  it("reports what is missing, and a rebuild makes downloads stale", () => {
    const onPending = vi.fn();
    const { result, rerender, unmount } = renderHook(
      ({ version }) => useDownloadTracker(version, FILES, onPending),
      { initialProps: { version: 1 } },
    );
    expect(onPending).toHaveBeenLastCalledWith(["the redacted PDF", "the label mapping"]);
    act(() => result.current.markDone("redacted"));
    expect(result.current.isDone("redacted")).toBe(true);
    expect(onPending).toHaveBeenLastCalledWith(["the label mapping"]);
    rerender({ version: 2 });
    expect(result.current.isDone("redacted")).toBe(false);
    expect(onPending).toHaveBeenLastCalledWith(["the redacted PDF", "the label mapping"]);
    unmount();
    expect(onPending).toHaveBeenLastCalledWith([]);
  });

  it("names the missing files in plain English", () => {
    expect(listing([])).toBe("");
    expect(listing(["a"])).toBe("a");
    expect(listing(["a", "b"])).toBe("a and b");
    expect(listing(["a", "b", "c"])).toBe("a, b and c");
  });
});

describe("leaving with files not downloaded", () => {
  function leave(): boolean {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  }

  it("asks only while something would be lost", () => {
    const { rerender, unmount } = renderHook(({ active }) => useLeaveWarning(active), {
      initialProps: { active: true },
    });
    expect(leave()).toBe(true);
    rerender({ active: false });
    expect(leave()).toBe(false);
    unmount();
  });
});

describe("empty master list", () => {
  it("shows a banner on Upload that opens the setup, even after skipping", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            total: 0,
            counts: {},
            issues: [],
            path: "C:/made/up/Names List - Organized.xlsx",
            age_seconds: null,
            needs_setup: false,
          }),
          { headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/No names loaded from the master list/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Set up master list" }));
    expect(
      screen.getByRole("dialog", { name: "Set up your shared master list" }),
    ).toBeInTheDocument();
  });
});
