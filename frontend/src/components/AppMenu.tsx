// The ⋯ menu: Start over, Help, Close the app. These were three sidebar
// controls; they are rarely used, so they fold away here.
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";

import { Button, Modal } from "./ui";

const HELP_URL =
  "https://github.com/ThuoBrian/finance-pii-redactor/blob/main/docs/troubleshooting.md";

const ITEM =
  "cursor-pointer rounded-md px-3 py-2 text-sm outline-none data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50 data-[highlighted]:bg-surface";

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
            className="rounded-lg px-2.5 py-1.5 text-lg leading-none hover:bg-surface"
          >
            ⋯
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={8}
            className="z-30 min-w-48 rounded-xl border border-border-soft bg-bg p-1 shadow-lg"
          >
            <DropdownMenu.Item
              className={ITEM}
              disabled={!canStartOver}
              onSelect={() => setConfirm("start-over")}
            >
              Start over
            </DropdownMenu.Item>
            <DropdownMenu.Item asChild className={ITEM}>
              <a href={HELP_URL} target="_blank" rel="noreferrer noopener">
                Help and troubleshooting ↗
              </a>
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 h-px bg-border-soft" />
            <DropdownMenu.Item className={ITEM} onSelect={() => setConfirm("close")}>
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
