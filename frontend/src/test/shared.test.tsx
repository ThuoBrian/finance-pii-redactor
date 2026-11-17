import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { DownloadStep, crosswalkWarning } from "../components/DownloadCards";
import { useFormatFlow } from "../components/useFormatFlow";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useFormatFlow", () => {
  it("runs a scan, then moves to Review with a fresh version", async () => {
    const goTo = vi.fn();
    const spec = {
      name: "test",
      scan: vi.fn(async () => ({ status: "running" })),
      review: vi.fn(async () => ({ mapping: [] as string[] })),
      apply: vi.fn(async () => ({ mapping: ["x"] })),
      download: vi.fn(async () => ({ excluded: [] })),
      expected: () => [{ kind: "redacted", label: "the file" }],
    };
    const { result } = renderHook(() => useFormatFlow("j", 1, goTo, () => {}, spec), { wrapper });
    act(() => result.current.scan.mutate({}));
    await waitFor(() => expect(result.current.scanning).toBe(true));
    act(() => result.current.progress.onDone());
    expect(result.current.scanning).toBe(false);
    expect(result.current.version).toBe(1);
    expect(goTo).toHaveBeenCalledWith(2);
  });

  it("a cancelled scan says so and keeps the step", async () => {
    const goTo = vi.fn();
    const spec = {
      name: "test2",
      scan: async () => ({}),
      review: async () => ({}),
      apply: async () => ({}),
      download: async () => ({ excluded: [] }),
      expected: () => [],
    };
    const { result } = renderHook(() => useFormatFlow("j", 1, goTo, () => {}, spec), { wrapper });
    act(() => result.current.progress.onCancelled());
    expect(result.current.scanNotice).toMatch(/cancelled/);
    expect(goTo).not.toHaveBeenCalled();
  });
});

describe("download step", () => {
  function Harness() {
    const info = useQuery({
      queryKey: ["info"],
      queryFn: async () => ({ excluded: ["salaries"], note: "hello" }),
    });
    return (
      <DownloadStep info={info} onBack={() => {}} onFinish={() => {}}>
        {(d) => <p>{d.note}</p>}
      </DownloadStep>
    );
  }

  it("shows the left-visible warning, the format's content and the footer", async () => {
    render(<Harness />, { wrapper });
    expect(await screen.findByText("hello")).toBeInTheDocument();
    expect(screen.getByText(/will not be hidden/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Redact another file" })).toBeInTheDocument();
  });

  it("words the names-file warning for codes or labels", () => {
    expect(crosswalkWarning("codes", "redacted file")).toContain("next to their codes");
    expect(crosswalkWarning("labels", "redacted PDF")).toContain("apart from the redacted PDF");
  });
});
