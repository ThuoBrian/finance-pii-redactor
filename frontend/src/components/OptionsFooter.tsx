// The bottom of every format's settings screen: any note or error from the
// last scan, then "Change file" and the one main button.
import { Button, Notice } from "./ui";

export function OptionsFooter({
  recommended,
  busy,
  disabled = false,
  notice,
  error,
  onBack,
  onScan,
}: {
  /** True when the settings are the recommended defaults. */
  recommended: boolean;
  busy: boolean;
  disabled?: boolean;
  notice: string | null;
  error: string | null;
  onBack: () => void;
  onScan: () => void;
}) {
  return (
    <>
      {notice && <Notice className="mt-4">{notice}</Notice>}
      {error && (
        <Notice tone="danger" className="mt-4">
          {error}
        </Notice>
      )}
      <div className="mt-6 flex items-center justify-between gap-3">
        <Button onClick={onBack}>Change file</Button>
        <Button variant="primary" disabled={disabled || busy} onClick={onScan}>
          {recommended ? "Redact with recommended settings" : "Redact with your settings"}
        </Button>
      </div>
    </>
  );
}
