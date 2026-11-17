// Master-list status in the top bar. The pill says how many names are
// loaded; the popover holds the detail that used to fill the sidebar card.
import * as Popover from "@radix-ui/react-popover";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, timeAgo, type MasterList } from "../api";
import { Icon } from "./Icon";
import { Button, Notice } from "./ui";

export function MasterListPill({
  data,
  isLoading,
  error,
}: {
  data: MasterList | undefined;
  isLoading: boolean;
  error: Error | null;
}) {
  const queryClient = useQueryClient();
  const refresh = useMutation({
    mutationFn: api.refreshMasterList,
    onSuccess: (fresh) => queryClient.setQueryData(["master-list"], fresh),
  });

  const warnings = data?.issues.filter((i) => i.severity === "warning").length ?? 0;
  const dot = !data
    ? "bg-border"
    : data.total === 0
      ? "bg-danger"
      : warnings
        ? "bg-warn"
        : "bg-success";
  const label = isLoading
    ? "Loading names..."
    : error
      ? "Master list unavailable"
      : data && data.total > 0
        ? `${data.total.toLocaleString()} names`
        : "No names loaded";

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-2 rounded-full border border-border-soft bg-card px-3 text-sm shadow-sm transition hover:bg-surface data-[state=open]:bg-surface"
          aria-label={`Master list: ${label}. Show details`}
        >
          <span aria-hidden className="relative flex h-2 w-2">
            <span className={`absolute inset-0 scale-[2] rounded-full opacity-25 ${dot}`} />
            <span className={`relative h-2 w-2 rounded-full ${dot}`} />
          </span>
          <span className="tabular whitespace-nowrap">{label}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="z-30 w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-border-soft bg-card p-4 text-sm shadow-lg"
        >
          <h2 className="font-semibold">Master list</h2>
          {error ? (
            <Notice tone="danger" className="mt-3">
              {error.message}
            </Notice>
          ) : data ? (
            <>
              <p className="mt-1 text-muted">
                {Object.entries(data.counts)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([cat, n]) => `${n.toLocaleString()} ${cat}`)
                  .join(" · ") || "No names loaded"}
                {data.age_seconds !== null &&
                  ` · updated ${timeAgo(data.age_seconds)}`}
              </p>
              {data.issues.length > 0 && (
                <details className="group mt-3 rounded-lg border border-border-soft">
                  <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-medium [&::-webkit-details-marker]:hidden">
                    <Icon
                      name="chevron-right"
                      className="h-3.5 w-3.5 text-muted transition-transform group-open:rotate-90"
                    />
                    {data.issues.length}{" "}
                    {data.issues.length === 1 ? "thing" : "things"} to tidy
                  </summary>
                  <ul className="max-h-64 space-y-3 overflow-y-auto px-3 pb-3">
                    {data.issues.map((issue) => (
                      <li key={issue.title}>
                        <p className="flex items-start gap-1.5 font-medium">
                          {issue.severity === "warning" && (
                            <>
                              <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 text-warn" />
                              <span className="sr-only">Warning: </span>
                            </>
                          )}
                          {issue.title}
                        </p>
                        <p className="text-muted">{issue.detail}</p>
                        <ul className="mt-1 list-disc pl-5 text-muted">
                          {issue.examples.map((ex) => (
                            <li key={ex}>{ex}</li>
                          ))}
                          {issue.total > issue.examples.length && (
                            <li>... and {issue.total - issue.examples.length} more</li>
                          )}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <p className="mt-3 break-all text-xs text-muted">{data.path}</p>
              <p className="mt-1 text-xs text-muted">
                To edit it: save and close the workbook in Excel, then Refresh.
              </p>
            </>
          ) : null}
          <Button
            className="mt-4 w-full"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
            <Icon name="refresh" className={`h-4 w-4 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Refreshing..." : "Refresh"}
          </Button>
          {refresh.error && (
            <Notice tone="danger" className="mt-3">
              {refresh.error.message}
            </Notice>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
