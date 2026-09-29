# Connecting to the shared Box master list

A quick guide for pointing your install at the team's shared master list in
Box, instead of an empty local one. Do this once, right after installing.

For the full reference (file format, data-quality checks, filename rules,
IT/scripted setup) see **[data/README.md](../data/README.md)**.

## Before you start

- **Get the app installed first** — see the [Quick start in the main
  README](../README.md#quick-start) if you haven't yet.
- **Ask your list owner for the Box folder** that holds
  `Names List - Organized.xlsx`. It must be a folder you already have access
  to in Box Drive — never a public or generally-shared one.
- **Make it available offline.** In Box Drive, right-click that folder and
  choose **Make Available Offline**. This keeps the app working even if your
  connection drops later.

## Connect the app

1. Launch the app (`run.bat` on Windows, `./run.sh` on macOS/Linux).
2. If it can't find a master list yet, it shows a **"Set up your shared
   master list"** dialog right in the browser.
3. Paste in the local path to the Box folder from the step above (something
   like `C:\Users\<you>\Box\Finance\Master List` on Windows, or
   `/Users/<you>/Box/Finance/Master List` on Mac). This is *your own*
   machine's path to the folder — Box can mount the same shared folder at a
   slightly different path on each person's computer, so don't copy someone
   else's path verbatim.
4. It takes effect immediately — no restart needed.

## Check it worked

Open **Advanced settings** in the app and look at the master-list summary:

- **Row counts look right** (roughly what a teammate already on the shared
  list sees) → you're connected.
- **Shows zero names** → the path is wrong, or the filename in Box isn't
  exactly `Names List - Organized.xlsx`. Double-check both before assuming
  the shared list itself is empty — see [data/README.md's filename
  rules](../data/README.md#keep-the-filename-exactly-as-is).

From here on, edit the workbook in place in Box (open, edit, save, close)
and refresh the app's browser tab to pick up changes — no restart needed.

## A note on the data itself

`Names List - Organized.xlsx` contains real names, so it's **Confidential**.
Keep it in Box, never copy it into this repo's local `data/` folder (which
is exactly what this setup avoids), and never paste its contents into
Claude or any other AI chat.
