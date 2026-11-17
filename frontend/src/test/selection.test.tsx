import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type ReviewRow } from "../api";
import { ExcelPreview } from "../components/excel/ExcelPreview";
import { PdfPreview } from "../components/pdf/PdfPreview";
import { ReviewLayout } from "../components/review/ReviewLayout";
import { HINTED, visibleRows } from "../components/review/ReviewList";

function row(term: string, source = "Model guess", hint = ""): ReviewRow {
  return {
    key: term.toLowerCase(),
    term,
    why: "Looks like a name",
    kind: "Person",
    source,
    confidence: 0.6,
    hint,
    occurrences: 1,
  };
}

function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("selecting a term", () => {
  const rows = [row("salaries", "Model guess", "ordinary word"), row("Jane Doe", "Master list")];
  const places: Record<string, number> = { salaries: 3, "jane doe": 1 };

  function renderReview() {
    const seen: (string | null)[] = [];
    render(
      <ReviewLayout
        heading="Review"
        summary=""
        rows={rows}
        filters={[]}
        clean={false}
        applied={[]}
        carried={[]}
        applying={false}
        applyError={null}
        onApply={vi.fn()}
        onBack={vi.fn()}
        onContinue={vi.fn()}
        occurrences={Object.entries(places).flatMap(([key, n]) => Array.from({ length: n }, () => ({ key })))}
        focusPanel="preview"
        panels={(selection) => {
          seen.push(selection ? `${selection.key}#${selection.place}` : null);
          return [
            { id: "mapping", label: "Mapping", content: <p>mapping</p> },
            { id: "preview", label: "Preview", content: <p>at {selection ? `${selection.key}#${selection.place}` : "nothing"}</p> },
          ];
        }}
      />,
    );
    return seen;
  }

  it("clicking a term switches to the preview and steps through its places", async () => {
    renderReview();
    expect(screen.getByText("mapping")).toBeInTheDocument();
    await userEvent.click(screen.getByText("salaries"));
    expect(screen.getByText("at salaries#0")).toBeInTheDocument();
    expect(screen.getByText(/place 1 of 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next place" }));
    expect(screen.getByText("at salaries#1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByText(/place \d of/)).toBeNull();
  });

  it("clicking the term does not tick or untick it", async () => {
    renderReview();
    await userEvent.click(screen.getByText("salaries"));
    expect(screen.getByRole("checkbox", { name: "Hide salaries" })).toBeChecked();
  });

  it("arrow keys move between rows and select them", async () => {
    renderReview();
    screen.getByRole("checkbox", { name: "Hide salaries" }).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("checkbox", { name: "Hide Jane Doe" })).toHaveFocus();
    expect(screen.getByText("at jane doe#0")).toBeInTheDocument();
    await userEvent.keyboard(" ");
    expect(screen.getByRole("checkbox", { name: "Hide Jane Doe" })).not.toBeChecked();
  });

  it("'Worth a closer look' shows only model guesses with a hint", () => {
    expect(visibleRows(rows, HINTED, "").map((r) => r.term)).toEqual(["salaries"]);
  });
});

describe("previews follow the selection", () => {
  it("the Excel preview opens the right block and outlines the cell", async () => {
    // Like the server, align any requested row to the start of its block.
    const preview = vi.spyOn(api.excel, "preview").mockImplementation(async (_job, tab, row) => {
      const start = row - (row % 500);
      return {
      tab,
      tabs: ["Jan", "Feb"],
      total_rows: 1200,
      start,
      page_size: 500,
      columns: ["Payee", "Notes"],
      original_columns: ["Payee", "Notes"],
      rows: Array.from({ length: 500 }, (_, i) => [`code ${start + i}`, "x"]),
      original_rows: Array.from({ length: 500 }, (_, i) => [`name ${start + i}`, "x"]),
      marked: [],
      elsewhere: 0,
      };
    });
    withQuery(
      <ExcelPreview
        jobId="j"
        version={1}
        focus={{ tab: 1, row: 702, column: "Notes", place: "cell", seq: 1 }}
      />,
    );
    await waitFor(() => expect(preview).toHaveBeenCalledWith("j", 1, 701));
    const cell = await waitFor(() => {
      const el = document.querySelector('[data-focus="true"]');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    // Row 702 is the 202nd row of the block starting at 500 (0-based 201).
    expect(cell.closest("tr")?.firstElementChild?.textContent).toBe("code 701");
    expect(cell.className).toContain("outline");
  });

  it("the PDF preview jumps to the selected page", async () => {
    const page = vi.spyOn(api.pdf, "page").mockResolvedValue("blob:fake");
    withQuery(<PdfPreview jobId="j" pageCount={5} version={1} focus={{ page: 4, seq: 1 }} />);
    await waitFor(() => expect(page).toHaveBeenCalledWith("j", 4, "redacted"));
    expect(await screen.findByRole("img", { name: /Page 4 of 5/ })).toBeInTheDocument();
  });
});
