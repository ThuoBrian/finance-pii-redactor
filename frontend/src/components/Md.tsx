// Renders the server's short notes, which use only **bold**, `code` and
// blank-line paragraphs. Text only: nothing is ever parsed as HTML.
import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="rounded bg-surface-2 px-1 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

export function Md({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/\n{2,}/)
        .filter((p) => p.trim())
        .map((p, i) => (
          <p key={i} className={i ? "mt-2" : undefined}>
            {inline(p)}
          </p>
        ))}
    </>
  );
}
