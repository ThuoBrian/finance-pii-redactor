// The confidence slider and the kinds of information to hide. Shared by
// every format's Options step, inside its collapsed "Customize" section.
import type { DetectionChoices, DetectionOptions } from "../api";
import { InfoTip } from "./InfoTip";

export function toggleIn<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export function DetectionFields({
  options,
  choices,
  onChange,
}: {
  options: DetectionOptions;
  choices: DetectionChoices;
  onChange: (next: DetectionChoices) => void;
}) {
  return (
    <>
      <div>
        <div className="flex items-center justify-between text-sm font-medium">
          <span className="inline-flex items-center">
            <label htmlFor="threshold">Confidence threshold</label>
            <InfoTip label="Confidence threshold">{options.threshold.help}</InfoTip>
          </span>
          <span className="font-mono">{choices.threshold.toFixed(2)}</span>
        </div>
        <input
          id="threshold"
          type="range"
          min={options.threshold.min}
          max={options.threshold.max}
          step={options.threshold.step}
          value={choices.threshold}
          onChange={(e) => onChange({ ...choices, threshold: Number(e.target.value) })}
          className="mt-2 w-full accent-[var(--primary)]"
        />
        <p className="mt-1 flex justify-between text-xs text-muted">
          <span>Catches more</span>
          <span>Catches less</span>
        </p>
      </div>

      <fieldset>
        <legend className="inline-flex items-center text-sm font-medium">
          Kinds of information to hide
          <InfoTip label="Kinds of information">{options.entity_help}</InfoTip>
        </legend>
        <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
          {options.entities.map((e) => (
            <label key={e.code} className="inline-flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={choices.entities.includes(e.code)}
                onChange={() =>
                  onChange({ ...choices, entities: toggleIn(choices.entities, e.code) })
                }
              />
              {e.label}
            </label>
          ))}
        </div>
      </fieldset>
    </>
  );
}

/** The collapsed Customize section that holds the less-used options. */
export function Customize({ hint, children }: { hint: string; children: React.ReactNode }) {
  return (
    <details className="mt-6 rounded-2xl border border-border-soft">
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2 px-5 py-4 font-medium">
        Customize
        <span className="text-sm font-normal text-muted">{hint}</span>
      </summary>
      <div className="space-y-6 border-t border-border-soft px-5 py-5">{children}</div>
    </details>
  );
}
