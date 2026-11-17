import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Stepper } from "../components/Stepper";

function currentLabel(): string | null {
  return document.querySelector('[aria-current="step"]')?.textContent ?? null;
}

describe("Stepper", () => {
  it("shows three stages, with settings counted as part of File", () => {
    const { rerender } = render(<Stepper current={0} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(currentLabel()).toContain("File");
    rerender(<Stepper current={1} />);
    expect(currentLabel()).toContain("File");
    rerender(<Stepper current={2} />);
    expect(currentLabel()).toContain("Review");
    rerender(<Stepper current={3} />);
    expect(currentLabel()).toContain("Download");
  });
});
