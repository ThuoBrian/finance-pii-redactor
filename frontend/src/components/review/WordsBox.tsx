// "Words or phrases to add", on the Review step: a name the master list and
// the model both missed can be typed here once the findings are on screen.
// Typed words are matched while the file is rebuilt, never by a rescan.
import { parseWords } from "../../api";
import { InfoTip } from "../InfoTip";
import { Button, Notice } from "../ui";

// A typed word shaped like this tool's own PDF label, e.g. "[001]".
const LABEL_SHAPED = /^\[\d+\]$/;

export function sameWords(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((w, i) => w === b[i]);
}

export function WordsBox({
  text,
  onTextChange,
  applied,
  busy,
  onAdd,
  warnLabelShaped = false,
  otherChanges = false,
}: {
  text: string;
  onTextChange: (text: string) => void;
  applied: string[];
  busy: boolean;
  onAdd: (words: string[]) => void;
  warnLabelShaped?: boolean;
  /** Another pending choice the same button applies (PDF table columns). */
  otherChanges?: boolean;
}) {
  const typed = parseWords(text);
  const changed = otherChanges || !sameWords(typed, applied);
  return (
    <div className="space-y-3">
      <div className="flex items-center text-sm font-medium">
        <label htmlFor="words">Words or phrases to add</label>
        <InfoTip label="Words or phrases to add">
          A name that is not on the master list and the model missed, a
          project codename, a case number. Each is redacted everywhere it
          appears, like a found name. Not saved anywhere once you start over.
        </InfoTip>
      </div>
      <textarea
        id="words"
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        rows={4}
        spellCheck={false}
        className="w-full rounded-lg border border-border bg-card shadow-sm px-3 py-2 text-sm"
        aria-describedby="words-help"
        placeholder="One per line"
      />
      <p id="words-help" className="text-xs text-muted">
        One word or phrase per line.
      </p>
      {warnLabelShaped && typed.some((w) => LABEL_SHAPED.test(w)) && (
        <Notice tone="warn">
          One of your words looks like a redaction label (for example [001]).
          That is the shape this tool writes into the PDF, so redacting it would
          redact the tool's own output. Remove it unless the document really
          contains that text for another reason.
        </Notice>
      )}
      <Button
        variant={changed ? "primary" : "secondary"}
        disabled={!changed || busy}
        onClick={() => onAdd(typed)}
        className="w-full"
      >
        {busy ? "Rebuilding..." : "Add and rebuild"}
      </Button>
    </div>
  );
}
