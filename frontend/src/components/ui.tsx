// Small shared building blocks. Kept in one file on purpose: a handful of
// styled elements, not a component library.
import * as Dialog from "@radix-ui/react-dialog";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-white shadow-sm hover:bg-primary-hover active:translate-y-px disabled:opacity-50",
  secondary:
    "border border-border/60 bg-card text-text shadow-sm hover:border-border hover:bg-surface active:translate-y-px disabled:opacity-50",
  danger: "bg-danger-solid text-white shadow-sm hover:opacity-90 active:translate-y-px disabled:opacity-50",
  ghost: "text-text hover:bg-surface disabled:opacity-40",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 rounded-md px-3 text-xs",
  md: "h-10 rounded-lg px-4 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button
      type={type}
      className={`inline-flex shrink-0 items-center justify-center gap-2 font-medium whitespace-nowrap transition disabled:cursor-not-allowed disabled:translate-y-0 ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

/** A square button that shows only an icon; ``label`` is its accessible name. */
export function IconButton({
  icon,
  label,
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string }) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted transition hover:bg-surface hover:text-text disabled:pointer-events-none disabled:opacity-40 ${className}`}
      {...props}
    >
      <Icon name={icon} />
    </button>
  );
}

type Tone = "info" | "warn" | "danger" | "success";

const TONES: Record<Tone, { box: string; icon: string; name: IconName }> = {
  info: { box: "border-border-soft bg-card", icon: "text-primary", name: "info" },
  warn: { box: "border-warn/30 bg-warn-soft", icon: "text-warn", name: "alert" },
  danger: { box: "border-danger/30 bg-danger-soft", icon: "text-danger", name: "alert" },
  success: { box: "border-success/30 bg-success-soft", icon: "text-success", name: "circle-check" },
};

export function Notice({
  tone = "info",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  const t = TONES[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`flex gap-3 rounded-xl border px-4 py-3 text-sm leading-relaxed text-text ${t.box} ${className}`}
    >
      <Icon name={t.name} className={`mt-0.5 h-4 w-4 ${t.icon}`} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

type BadgeTone = "neutral" | "info" | "success" | "warn" | "danger";

const BADGES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-muted",
  info: "bg-primary-soft text-link",
  success: "bg-success-soft text-success",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${BADGES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span
        aria-hidden
        className="h-4 w-4 animate-spin rounded-full border-2 border-border-soft border-t-primary"
      />
      {label}
    </span>
  );
}

/** Grey shapes where content is about to appear. ``label`` is read out. */
export function Skeleton({ label, lines = 3 }: { label: string; lines?: number }) {
  return (
    <div role="status" className="card space-y-3 p-5">
      <span className="sr-only">{label}</span>
      <div aria-hidden className="h-5 w-1/3 animate-pulse rounded-md bg-surface-2" />
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          aria-hidden
          className="h-3.5 animate-pulse rounded bg-surface-2"
          style={{ width: `${92 - ((i * 17) % 40)}%` }}
        />
      ))}
    </div>
  );
}

/** A centred modal with a title, used for confirmations and setup. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border-soft bg-card p-6 shadow-lg">
          <Dialog.Title className="pr-8 text-lg font-semibold">{title}</Dialog.Title>
          {description ? (
            <Dialog.Description className="mt-2 text-sm leading-relaxed text-muted">
              {description}
            </Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">{title}</Dialog.Description>
          )}
          <div className="mt-6">{children}</div>
          {/* Last in the DOM, so opening the dialog focuses its first real
              control, not the close button. */}
          <Dialog.Close asChild>
            <IconButton icon="x" label="Dismiss" className="absolute right-3 top-3" />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** The product mark: a shield with a tick, on a soft rounded tile. */
export function ShieldMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-gradient-to-b from-[#3b82f6] to-[#1d4ed8] shadow-sm ring-1 ring-inset ring-white/15 ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-[62%] w-[62%]" fill="none">
        <path
          fill="rgb(255 255 255 / 0.18)"
          stroke="#fff"
          strokeWidth="1.8"
          strokeLinejoin="round"
          d="M12 2.5 4.5 5.4v5.7c0 4.6 3.1 8.8 7.5 10.4 4.4-1.6 7.5-5.8 7.5-10.4V5.4z"
        />
        <path
          stroke="#fff"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m8.6 12 2.4 2.4 4.4-4.6"
        />
      </svg>
    </span>
  );
}
