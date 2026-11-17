import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Md } from "../components/Md";

describe("Md", () => {
  it("renders bold and code, never HTML", () => {
    const { container } = render(
      <Md text={"**2 scanned pages.** Check `[001]`.\n\n<img src=x onerror=alert(1)>"} />,
    );
    expect(screen.getByText("2 scanned pages.").tagName).toBe("STRONG");
    expect(screen.getByText("[001]").tagName).toBe("CODE");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelectorAll("p")).toHaveLength(2);
  });
});
