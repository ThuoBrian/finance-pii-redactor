// The ⋯ menu: Start over, Help, Close the app. These were three sidebar
// controls; they are rarely used, so they fold away here.
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";

import { Icon } from "./Icon";
import { Button, Modal } from "./ui";

const HELP_URL =
  "https://github.com/ThuoBrian/finance-pii-redactor/blob/main/docs/troubleshooting.md";

const ITEM =
  "flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm outline-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50 data-[highlighted]:bg-surface";

export function AppMenu({
  canStartOver,
  onStartOver,
  onClose,
  notDownloaded = "",
}: {
  canStartOver: boolean;
  onStartOver: () => void;
  onClose: () => void;
  /** e.g. "the redacted PDF and the label mapping"; empty when nothing is missing. */
  notDownloaded?: string;
}) {
  const lost = notDownloaded
    ? `You haven't downloaded ${notDownloaded} yet; it will be lost.`
    : "Anything not yet downloaded will be lost.";
  const [confirm, setConfirm] = useState<"start-over" | "close" | null>(null);

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            type="button"
            aria-label="Menu"
            title="Menu"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted transition hover:bg-surface hover:text-text data-[state=open]:bg-surface data-[state=open]:text-text"
          >
            <Icon name="more" className="h-5 w-5" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={8}
            className="z-30 min-w-56 rounded-xl border border-border-soft bg-card p-1.5 shadow-lg"
          >
            <DropdownMenu.Item
              className={ITEM}
              disabled={!canStartOver}
              onSelect={() => setConfirm("start-over")}
            >
              <Icon name="rotate-ccw" className="h-4 w-4 text-muted" />
              Start over
            </DropdownMenu.Item>
            <DropdownMenu.Item asChild className={ITEM}>
              <a href={HELP_URL} target="_blank" rel="noreferrer noopener">
                <Icon name="help" className="h-4 w-4 text-muted" />
                Help and troubleshooting
                <Icon name="external" className="ml-auto h-3.5 w-3.5 text-muted" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 h-px bg-border-soft" />
            <DropdownMenu.Item className={`${ITEM} text-danger`} onSelect={() => setConfirm("close")}>
              <Icon name="power" className="h-4 w-4" />
              Close the app
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Modal
        open={confirm === "start-over"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Start over?"
        description={`This removes the file and everything built from it. ${lost}`}
      >
        <div className="flex justify-end gap-2">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => {
              setConfirm(null);
              onStartOver();
            }}
          >
            Start over
          </Button>
        </div>
      </Modal>

      <Modal
        open={confirm === "close"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Close the app?"
        description={`This fully quits the tool and closes its window. ${lost}`}
      >
        <div className="flex justify-end gap-2">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => {
              setConfirm(null);
              onClose();
            }}
          >
            Close the app
          </Button>
        </div>
      </Modal>
    </>
  );
}
