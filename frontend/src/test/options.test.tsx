import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import { Profiler } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type ExcelOptions as Options } from "../api";
import { ExcelOptions, defaultChoices } from "../components/excel/ExcelOptions";

const OPTIONS: Options = {
  tabs: [{ name: "Jan", columns: ["Payee"], default_columns: [0] }],
  summary: "1 tab (Jan)",
  threshold: { default: 0.35, min: 0.1, max: 0.85, step: 0.05, help: "help" },
  entities: [{ code: "PERSON", label: "Person" }],
  entity_help: "kinds",
};

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Excel options", () => {
  it("settles instead of re-rendering on a timer", async () => {
    vi.useFakeTimers();
    vi.spyOn(api.excel, "estimate").mockResolvedValue({ warning: null });
    const choices = defaultChoices(OPTIONS);
    let renders = 0;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <Profiler id="options" onRender={() => renders++}>
          <ExcelOptions
            jobId="j"
            options={OPTIONS}
            choices={choices}
            onChange={() => {}}
            onScan={() => {}}
            onBack={() => {}}
            busy={false}
            error={null}
            recommended
          />
        </Profiler>
      </QueryClientProvider>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    const settled = renders;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(renders).toBe(settled);
  });
});
