import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { parseWords } from "../api";
import { WordsBox } from "../components/review/WordsBox";

function Harness({ onAdd, warn = false }: { onAdd: (w: string[]) => void; warn?: boolean }) {
  const [text, setText] = useState("");
  return (
    <WordsBox text={text} onTextChange={setText} applied={[]} busy={false} onAdd={onAdd} warnLabelShaped={warn} />
  );
}

describe("words box", () => {
  it("parses lines, trimming blanks", () => {
    expect(parseWords(" Project Falcon \n\n case 42\r\n")).toEqual(["Project Falcon", "case 42"]);
  });

  it("enables Add only once something new is typed, and sends the words", async () => {
    const onAdd = vi.fn();
    render(<Harness onAdd={onAdd} />);
    const button = screen.getByRole("button", { name: "Add and rebuild" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Words or phrases to add"), "Project Falcon");
    await userEvent.click(button);
    expect(onAdd).toHaveBeenCalledWith(["Project Falcon"]);
  });

  it("warns about a label-shaped word only where labels exist (PDF)", async () => {
    const { unmount } = render(<Harness onAdd={vi.fn()} warn />);
    await userEvent.type(screen.getByLabelText("Words or phrases to add"), "[[001]");
    expect(screen.getByText(/looks like a redaction label/)).toBeInTheDocument();
    unmount();
    render(<Harness onAdd={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Words or phrases to add"), "[[001]");
    expect(screen.queryByText(/looks like a redaction label/)).toBeNull();
  });
});
