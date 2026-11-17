import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ReviewRow } from "../api";
import { ReviewLayout } from "../components/review/ReviewLayout";
import { visibleRows } from "../components/review/ReviewList";

function row(term: string, source = "Model guess"): ReviewRow {
  return {
    key: term.toLowerCase(),
    term,
    why: "Looks like a name",
    kind: "Person",
    source,
    confidence: 0.6,
    hint: "",
    occurrences: 1,
  };
}

const ROWS = [row("salaries"), row("Acme Widgets"), row("Jane Doe", "Master list")];

function renderReview(overrides: Partial<Parameters<typeof ReviewLayout>[0]> = {}) {
  const props = {
    heading: "Review what was found",
    summary: "3 terms found",
    rows: ROWS,
    filters: [],
    clean: false,
    applied: [] as string[],
    carried: [] as string[],
    panels: () => [{ id: "p", label: "Preview", content: <p>preview</p> }],
    applying: false,
    applyError: null,
    onApply: vi.fn(),
    onBack: vi.fn(),
    onContinue: vi.fn(),
    ...overrides,
  };
  render(<ReviewLayout {...props} />);
  return props;
}

describe("review", () => {
  it("starts with every term ticked and Continue enabled", () => {
    renderReview();
    const list = screen.getByRole("list", { name: "Detected terms" });
    expect(within(list).getAllByRole("checkbox").every((c) => (c as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByText("3 terms found")).toBeInTheDocument();
    expect(screen.getByText("3 terms", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to download" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Apply changes" })).toBeDisabled();
  });

  it("holds Continue until an untick is applied, then sends the key", async () => {
    const props = renderReview();
    await userEvent.click(screen.getByRole("checkbox", { name: /salaries/ }));
    expect(screen.getByText(/1 change not applied/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to download" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Apply changes (1)" }));
    expect(props.onApply).toHaveBeenCalledWith(["salaries"]);
  });

  it("re-ticking an untick undoes the change", async () => {
    renderReview();
    const box = screen.getByRole("checkbox", { name: /salaries/ });
    await userEvent.click(box);
    await userEvent.click(box);
    expect(screen.getByRole("button", { name: "Continue to download" })).toBeEnabled();
  });

  it("shows applied unticks as left visible", () => {
    renderReview({ applied: ["salaries"] });
    expect(screen.getByRole("checkbox", { name: /salaries/ })).not.toBeChecked();
    expect(screen.getByText(/1 left visible/)).toBeInTheDocument();
  });

  it("folds a clean run behind Review anyway", async () => {
    renderReview({ clean: true });
    expect(screen.getByText(/Nothing here is a guess/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Review anyway" }));
    expect(screen.getByRole("list", { name: "Detected terms" })).toBeInTheDocument();
  });

  it("filters and searches without touching ticks", () => {
    expect(visibleRows(ROWS, "Master list", "").map((r) => r.term)).toEqual(["Jane Doe"]);
    expect(visibleRows(ROWS, null, "ACME").map((r) => r.term)).toEqual(["Acme Widgets"]);
    expect(visibleRows(ROWS, null, "  ")).toHaveLength(3);
  });
});

describe("review hold", () => {
  it("holds Continue while typed words are not added", () => {
    renderReview({ hold: "typed words not added yet", additions: <p>words</p> });
    expect(screen.getByRole("button", { name: "Continue to download" })).toBeDisabled();
    expect(screen.getByText(/typed words not added yet/)).toBeInTheDocument();
  });
});
