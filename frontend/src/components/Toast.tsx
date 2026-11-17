// A brief confirmation at the bottom of the screen that clears itself.
// For news, not warnings: anything the user must act on stays a Notice.
import { useEffect, type ReactNode } from "react";

import { Icon } from "./Icon";

export const TOAST_MS = 4000;

export function Toast({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    const id = setTimeout(onClose, TOAST_MS);
    return () => clearTimeout(id);
  }, [onClose]);
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-24 left-1/2 z-30 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-3 rounded-xl bg-text py-2 pl-3.5 pr-2 text-sm text-bg shadow-lg"
    >
      <Icon name="circle-check" className="h-4 w-4 opacity-80" />
      <span>{children}</span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onClose}
        className="inline-flex h-7 w-7 items-center justify-center rounded-md opacity-70 transition hover:opacity-100"
      >
        <Icon name="x" className="h-4 w-4" />
      </button>
    </div>
  );
}
