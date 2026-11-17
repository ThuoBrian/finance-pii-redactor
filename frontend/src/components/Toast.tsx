// A brief confirmation at the bottom of the screen that clears itself.
// For news, not warnings: anything the user must act on stays a Notice.
import { useEffect, type ReactNode } from "react";

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
      className="fixed bottom-20 left-1/2 z-30 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-3 rounded-lg bg-text px-4 py-2.5 text-sm text-bg shadow-lg"
    >
      <span>{children}</span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onClose}
        className="rounded px-1 opacity-80 hover:opacity-100"
      >
        ×
      </button>
    </div>
  );
}
