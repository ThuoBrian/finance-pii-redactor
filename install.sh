#!/usr/bin/env bash
# install.sh - one-line installer for the Finance PII Redactor (macOS/Linux).
#
# Paste into a terminal (nothing else required):
#
#   curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
#
# It asks where to install, downloads the latest version there, and starts the
# app. The first launch sets up the environment (a few minutes, once).
# To skip the prompt, set FPR_INSTALL_DIR before running.

set -euo pipefail

REPO="ThuoBrian/finance-pii-redactor"
BRANCH="main"
APP_NAME="finance-pii-redactor"
DATA_REL="data/Names List - Organized.xlsx"

# Colors, but only when writing to a real terminal.
if [ -t 1 ]; then
    GREEN=$'\033[1;32m'; CYAN=$'\033[1;36m'; RESET=$'\033[0m'
else
    GREEN=""; CYAN=""; RESET=""
fi

# Return the parent folder to install into (the app folder is created inside it).
# Prompts on the terminal; when piped via `curl | bash`, reads must come from
# /dev/tty or they would consume the piped script instead of user input.
choose_install_root() {
    if [ -n "${FPR_INSTALL_DIR:-}" ]; then
        printf '%s' "$FPR_INSTALL_DIR"
        return
    fi

    local desktop="$HOME/Desktop"
    [ -d "$desktop" ] || desktop="$HOME"

    if [ ! -r /dev/tty ]; then
        printf '%s' "$desktop"
        return
    fi

    {
        printf '\n'
        printf 'Where should Finance PII Redactor be installed?\n'
        printf '  [1] Desktop (default)\n'
        printf '  [2] Documents\n'
        printf '  [3] Home folder\n'
        printf '  [4] Type a path\n'
        printf 'Enter 1-4 (or press Enter for Desktop): '
    } > /dev/tty

    local choice=""
    read -r choice < /dev/tty || true
    case "$choice" in
        2) printf '%s' "$HOME/Documents" ;;
        3) printf '%s' "$HOME" ;;
        4)
            printf 'Full path to the folder to install into: ' > /dev/tty
            local p=""
            read -r p < /dev/tty || true
            case "$p" in
                "")   printf '%s' "$desktop" ;;
                "~"*) printf '%s' "${p/#\~/$HOME}" ;;
                *)    printf '%s' "$p" ;;
            esac
            ;;
        *) printf '%s' "$desktop" ;;
    esac
}

printf '\n%sFinance PII Redactor - installer%s\n' "$GREEN" "$RESET"

INSTALL_ROOT="$(choose_install_root)"
TARGET="$INSTALL_ROOT/$APP_NAME"
printf '%sInstalling to: %s%s\n\n' "$GREEN" "$TARGET" "$RESET"

# 1. Download the current source as a tarball (public repo, no login).
TARBALL_URL="https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

printf '%sDownloading the latest version...%s\n' "$CYAN" "$RESET"
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$TARBALL_URL" -o "$TMP_DIR/src.tar.gz"
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_DIR/src.tar.gz" "$TARBALL_URL"
else
    printf 'Error: this installer needs curl or wget.\n' >&2
    exit 1
fi

# 2. Extract (the tarball contains a single top-level <repo>-<branch> folder).
tar -xzf "$TMP_DIR/src.tar.gz" -C "$TMP_DIR"
EXTRACTED="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

# 3. Preserve a local master list (it is intentionally not shipped in the repo).
SAVED_MASTER=""
if [ -f "$TARGET/$DATA_REL" ]; then
    printf '%sPreserving your existing master list...%s\n' "$CYAN" "$RESET"
    SAVED_MASTER="$TMP_DIR/Names List - Organized.xlsx.bak"
    cp "$TARGET/$DATA_REL" "$SAVED_MASTER"
fi

# 4. Put the new version in place.
mkdir -p "$INSTALL_ROOT"
rm -rf "$TARGET"
mv "$EXTRACTED" "$TARGET"
if [ -n "$SAVED_MASTER" ]; then
    mkdir -p "$(dirname "$TARGET/$DATA_REL")"
    cp "$SAVED_MASTER" "$TARGET/$DATA_REL"
fi

printf '\n%sDone. Starting the app (first run sets up the environment)...%s\n\n' "$GREEN" "$RESET"

# 5. Launch. run.sh resolves its own location; use bash so no +x bit is needed.
cd "$TARGET"
bash "$TARGET/run.sh"
