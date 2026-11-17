// A small "?" that opens a short explanation, in place of help paragraphs
// that would sit on screen all the time. Click (or Enter/Space) opens it, so
// it works by keyboard and touch, not only on hover.
import * as Popover from "@radix-ui/react-popover";
import type { ReactNode } from "react";

import { Icon } from "./Icon";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={`About ${label}`}
          className="ml-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full align-middle text-muted transition hover:bg-surface hover:text-text"
        >
          <Icon name="help" className="h-4 w-4" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={6}
          className="z-50 max-w-xs rounded-lg border border-border-soft bg-card p-3 text-xs font-normal leading-relaxed text-text shadow-lg"
        >
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
