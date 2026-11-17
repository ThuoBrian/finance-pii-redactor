// What every format flow shares once a file is uploaded: the background scan
// and its progress, the review (rebuilt on every Apply), the download info,
// and which files have been downloaded. Each flow passes its own API calls.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import { useDownloadTracker, type ExpectedFile } from "./DownloadCards";

export type FlowSpec<ScanBody, ApplyArgs, Review, Info> = {
  /** Query-key prefix, e.g. "excel" (gives "excel-review", "excel-download"). */
  name: string;
  scan: (body: ScanBody) => Promise<unknown>;
  review: () => Promise<Review>;
  apply: (args: ApplyArgs) => Promise<Review>;
  download: () => Promise<Info>;
  /** The files the user should leave with, for the not-downloaded warning. */
  expected: (review: Review) => ExpectedFile[];
};

export function useFormatFlow<ScanBody, ApplyArgs, Review, Info>(
  jobId: string,
  step: 1 | 2 | 3,
  goTo: (step: 0 | 1 | 2 | 3) => void,
  onPending: (missing: string[]) => void,
  spec: FlowSpec<ScanBody, ApplyArgs, Review, Info>,
) {
  const queryClient = useQueryClient();
  // Bumped on every new result, so the review, previews and download refetch.
  const [version, setVersion] = useState(0);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanNotice, setScanNotice] = useState<string | null>(null);

  const review = useQuery({
    queryKey: [`${spec.name}-review`, jobId, version],
    queryFn: spec.review,
    enabled: step >= 2 && !scanning,
  });
  const info = useQuery({
    queryKey: [`${spec.name}-download`, jobId, version],
    queryFn: spec.download,
    enabled: step === 3,
  });
  const scan = useMutation({
    mutationFn: spec.scan,
    onMutate: () => {
      setScanError(null);
      setScanNotice(null);
    },
    onSuccess: () => setScanning(true),
    onError: (e) => setScanError(e.message),
  });
  const apply = useMutation({
    mutationFn: spec.apply,
    onSuccess: (fresh) => {
      queryClient.setQueryData([`${spec.name}-review`, jobId, version + 1], fresh);
      setVersion((v) => v + 1);
    },
  });

  const reviewData = review.data;
  const expected = useMemo(
    () => (reviewData ? spec.expected(reviewData) : []),
    [reviewData], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const tracker = useDownloadTracker(version, expected, onPending);

  // Stable, because TaskProgress reports through them from an effect.
  const onDone = useCallback(() => {
    setScanning(false);
    setVersion((v) => v + 1);
    goTo(2);
  }, [goTo]);
  const onCancelled = useCallback(() => {
    setScanning(false);
    setScanNotice("Scan cancelled. Nothing was changed.");
  }, []);
  const onError = useCallback((message: string) => {
    setScanning(false);
    setScanError(message);
  }, []);

  return {
    version,
    scanning,
    scanError,
    scanNotice,
    scan,
    review,
    apply,
    info,
    tracker,
    progress: { onDone, onCancelled, onError },
  };
}
