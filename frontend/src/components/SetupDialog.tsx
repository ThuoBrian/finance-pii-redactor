// First-run prompt for the shared master-list folder, shown when no names
// loaded and the user has not chosen "Skip for now".
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type MasterList } from "../api";
import { Button, Modal, Notice } from "./ui";
import { useDebounced } from "./useDebounced";

const FILENAME = "Names List - Organized.xlsx";

export function SetupDialog({
  open,
  onDismiss,
  currentPath,
}: {
  open: boolean;
  onDismiss: () => void;
  currentPath: string;
}) {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState("");
  const [saveAnyway, setSaveAnyway] = useState(false);
  const typed = useDebounced(folder.trim(), 300);

  const check = useQuery({
    queryKey: ["folder-check", typed],
    queryFn: () => api.checkFolder(typed),
    enabled: typed.length > 0,
  });
  const found = typed.length > 0 && check.data?.found === true;

  const done = (fresh: MasterList) => {
    queryClient.setQueryData(["master-list"], fresh);
    onDismiss();
  };
  const save = useMutation({
    mutationFn: () => api.saveFolder(folder.trim(), !found && saveAnyway),
    onSuccess: done,
  });
  const skip = useMutation({ mutationFn: api.skipSetup, onSuccess: done });

  return (
    <Modal
      open={open}
      onOpenChange={(next) => !next && onDismiss()}
      title="Set up your shared master list"
      description={
        <>
          No names were found in the master list. If your team keeps a shared
          copy of <strong>{FILENAME}</strong> (for example in a Box folder),
          paste its folder path below. No restart needed.
        </>
      }
    >
      <label className="block text-sm font-medium" htmlFor="ml-folder">
        Folder containing the master list
      </label>
      <input
        id="ml-folder"
        value={folder}
        onChange={(e) => {
          setFolder(e.target.value);
          setSaveAnyway(false);
        }}
        placeholder="C:\Users\you\Box\Team\Master List Folder"
        className="mt-1 w-full rounded-lg border border-border bg-card shadow-sm px-3 py-2 text-sm"
        autoComplete="off"
        spellCheck={false}
      />
      <p className="mt-1 break-all text-xs text-muted">
        Currently reading from: {currentPath}
      </p>

      {typed && check.data && (
        <div className="mt-3">
          {found ? (
            <Notice tone="success">Found {FILENAME} in this folder.</Notice>
          ) : (
            <Notice tone="warn">
              {FILENAME} was not found at this exact path yet. Double-check it.
              If the folder is still syncing in Box, you can save it anyway.
              <label className="mt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={saveAnyway}
                  onChange={(e) => setSaveAnyway(e.target.checked)}
                />
                Save anyway: the folder is still syncing
              </label>
            </Notice>
          )}
        </div>
      )}
      {(save.error || skip.error) && (
        <Notice tone="danger" className="mt-3">
          {(save.error ?? skip.error)?.message}
        </Notice>
      )}

      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <Button onClick={() => skip.mutate()} disabled={skip.isPending}>
          Skip for now
        </Button>
        <Button
          variant="primary"
          onClick={() => save.mutate()}
          disabled={!(found || saveAnyway) || save.isPending}
        >
          Save and use this folder
        </Button>
      </div>
      <p className="mt-4 text-xs text-muted">
        No shared folder? Skip this. Names are still pseudonymized, with flagged
        auto-generated IDs instead of your team's curated ones.
      </p>
    </Modal>
  );
}
