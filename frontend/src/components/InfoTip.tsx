// A small "?" that opens a short explanation, in place of help paragraphs
// that would sit on screen all the time. Click (or Enter/Space) opens it, so
// it works by keyboard and touch, not only on hover.
import * as Popover from "@radix-ui/react-popover";
import type { ReactNode } from "react";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`About ${label}`}
          className="ml-1.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border-soft align-middle text-[0.7rem] font-semibold text-muted hover:bg-surface"
        >
          ?
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg border border-border-soft bg-bg p-3 text-xs font-normal leading-relaxed text-text shadow-lg"
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
