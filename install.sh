#!/usr/bin/env bash
# install.sh - one-line installer for the Finance PII Redactor (macOS/Linux).
#
# Paste into a terminal (nothing else required):
#
#   curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
#
# It asks where to install, downloads the latest version there, and starts the
# app. The first launch sets up the environment (a few minutes, once).
# Running it again updates an existing install: it asks first, keeps the old
# copy until the new one is in place, and never replaces a folder that is not
# an install. To skip the prompts, set FPR_INSTALL_DIR before running.
#
# Master list note: this script only preserves a master list kept locally at
# <install>/data/Names List - Organized.xlsx. If your team instead points
# installs at a shared Box folder via FPR_MASTER_LIST_DIR (see
# data/README.md), that setup lives entirely outside this script's install
# folder, so it is untouched by install/update either way - but this script
# also does NOT set FPR_MASTER_LIST_DIR up for you on a first run. A
# brand-new machine still needs that one-time env-var setup done separately.
#
# Keep this file pure ASCII with LF endings (see docs/troubleshooting.md).

set -Eeuo pipefail

REPO="ThuoBrian/finance-pii-redactor"
BRANCH="main"
APP_NAME="finance-pii-redactor"
DATA_REL="data/Names List - Organized.xlsx"
ONE_LINER="curl -fsSL https://raw.githubusercontent.com/$REPO/$BRANCH/install.sh | bash"

# -- Colours & styling --------------------------------------------------------
# Only when writing to a real terminal, and never when NO_COLOR is set.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RESET=$'\033[0m'; BOLD=$'\033[1;37m'; DIM=$'\033[2m'
    YELLOW=$'\033[1;33m'; RED=$'\033[1;31m'
    # IPA brand colour (primary green #49ac57) - 24-bit truecolor
    IPA_GREEN=$'\033[38;2;73;172;87m'
else
    RESET=""; BOLD=""; DIM=""; YELLOW=""; RED=""; IPA_GREEN=""
fi

rule()    { printf ' %s%s%s\n' "$IPA_GREEN" "====================================================================" "$RESET"; }
step()    { printf '\n   %s[ Step %s of %s ]%s %s%s%s\n' "$IPA_GREEN" "$1" "$2" "$RESET" "$BOLD" "$3" "$RESET"; }
ok()      { printf '      %s[OK]%s %s\n' "$IPA_GREEN" "$RESET" "$1"; }
info()    { printf '      %s[INFO]%s %s\n' "$DIM" "$RESET" "$1"; }
note()    { printf '      %s[NOTE]%s %s\n' "$YELLOW" "$RESET" "$1"; }
hint()    { printf '      %s%s%s\n' "$DIM" "$1" "$RESET"; }
problem() { printf '\n      %s[PROBLEM]%s %s\n' "$RED" "$RESET" "$1"; }

# True when a terminal can be prompted. When piped via `curl | bash`, reads
# must come from /dev/tty or they would consume the piped script instead of
# user input; with no controlling terminal at all, opening it fails.
has_tty() { { : < /dev/tty; } 2>/dev/null; }

# Ask a yes/no question on the terminal. Enter means yes; no terminal means yes.
ask_yes() {
    has_tty || return 0
    printf '%s' "$1" > /dev/tty
    local answer=""
    read -r answer < /dev/tty || true
    case "$(printf '%s' "$answer" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')" in
        "" | y | yes) return 0 ;;
        *) return 1 ;;
    esac
}

# Show a spinner while a background job runs (same as run.sh), then return its
# exit status.
spin() {
    local pid=$1 message=$2 chars='|/-\' i=0
    if [ -t 1 ]; then
        while kill -0 "$pid" 2>/dev/null; do
            printf '\r      %s %s' "${IPA_GREEN}${chars:i:1}${RESET}" "$message"
            i=$(((i + 1) % 4))
            sleep 0.1
        done
        printf '\r%*s\r' "$((${#message} + 12))" ""
    fi
    wait "$pid"
}

# Return the parent folder to install into (the app folder is created inside it).
# The menu goes to the terminal; only the chosen path goes to stdout.
choose_install_root() {
    if [ -n "${FPR_INSTALL_DIR:-}" ]; then
        printf '%s' "$FPR_INSTALL_DIR"
        return
    fi

    local desktop="$HOME/Desktop"
    [ -d "$desktop" ] || desktop="$HOME"

    if ! has_tty; then
        printf '%s' "$desktop"
        return
    fi

    {
        printf '\n'
        printf '      Where should Finance PII Redactor be installed?\n'
        printf '        [1] Desktop (default)\n'
        printf '        [2] Documents\n'
        printf '        [3] Home folder\n'
        printf '        [4] Type a path\n'
        printf '      Enter 1-4 (or press Enter for Desktop): '
    } > /dev/tty

    local choice=""
    read -r choice < /dev/tty || true
    case "$choice" in
        2) printf '%s' "$HOME/Documents" ;;
        3) printf '%s' "$HOME" ;;
        4)
            printf '      Full path to the folder to install into: ' > /dev/tty
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

TMP_DIR=""
TARGET=""
BACKUP=""

# On any exit before the new version is fully in place, put the old one back.
cleanup() {
    if [ -n "$BACKUP" ] && [ -d "$BACKUP" ]; then
        rm -rf "$TARGET"
        if mv "$BACKUP" "$TARGET"; then
            info "Your previous version was put back."
        else
            note "Your previous version is saved at $BACKUP"
        fi
    fi
    [ -z "$TMP_DIR" ] || rm -rf "$TMP_DIR"
}
trap cleanup EXIT

on_error() {
    problem "The installer stopped unexpectedly (line $1)."
    hint "Fix the problem above (often the internet connection), then paste the install line again:"
    hint "  $ONE_LINER"
}
trap 'on_error $LINENO' ERR

# -- Banner -------------------------------------------------------------------
printf '\n'
rule
printf '\n'
printf '     %s%s%s\n' "$BOLD" "FINANCE PII REDACTOR  -  INSTALLER" "$RESET"
printf '     %s%s%s\n' "$DIM" "Removes names and organizations from your Excel, PDF and Word files." "$RESET"
printf '     %s%s%s\n' "$IPA_GREEN" "Runs 100% on your computer - nothing is ever uploaded." "$RESET"
printf '\n'
rule

# -- 1. Choose a folder -------------------------------------------------------
step 1 4 "Choosing where to install"
INSTALL_ROOT="$(choose_install_root)"
TARGET="$INSTALL_ROOT/$APP_NAME"
IS_UPDATE=""

if [ -e "$TARGET" ]; then
    if [ ! -f "$TARGET/app.py" ] || [ ! -f "$TARGET/pyproject.toml" ]; then
        problem "$TARGET already exists, but it is not a Finance PII Redactor install."
        hint "Nothing was changed. Run the installer again and choose a different folder."
        exit 1
    fi
    IS_UPDATE=1
    info "Found an existing install at $TARGET"
    info "Updating replaces the program files. Your master list is kept."
    if [ -z "${FPR_INSTALL_DIR:-}" ] && ! ask_yes "      Update it? [Y/n]: "; then
        hint "Cancelled. Nothing was changed."
        exit 0
    fi
fi
ok "Installing to $TARGET"

# -- 2. Download (public repo, no login) --------------------------------------
step 2 4 "Downloading the latest version"
TARBALL_URL="https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
TMP_DIR="$(mktemp -d)"

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$TARBALL_URL" -o "$TMP_DIR/src.tar.gz" &
elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_DIR/src.tar.gz" "$TARBALL_URL" &
else
    problem "This installer needs curl or wget."
    exit 1
fi
if ! spin $! "Downloading, please wait..."; then
    problem "The download failed."
    hint "Check your internet connection, then paste the install line again:"
    hint "  $ONE_LINER"
    exit 1
fi
ok "Downloaded $(awk -v b="$(wc -c < "$TMP_DIR/src.tar.gz")" 'BEGIN { printf "%.1f", b / 1048576 }') MB."

# The tarball contains a single top-level <repo>-<branch> folder.
mkdir "$TMP_DIR/src"
tar -xzf "$TMP_DIR/src.tar.gz" -C "$TMP_DIR/src"
EXTRACTED="$(find "$TMP_DIR/src" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
ok "Unpacked."

# -- 3. Install ---------------------------------------------------------------
step 3 4 "Putting the program in place"

# The master list is intentionally not shipped in the repo, so carry it over.
SAVED_MASTER=""
if [ -f "$TARGET/$DATA_REL" ]; then
    SAVED_MASTER="$TMP_DIR/master-list.xlsx"
    cp "$TARGET/$DATA_REL" "$SAVED_MASTER"
    ok "Saved a copy of your master list."
fi

mkdir -p "$INSTALL_ROOT"

# Move the old version aside rather than deleting it, so a failure below
# can put it back (see cleanup).
if [ -n "$IS_UPDATE" ]; then
    backup_path="$TARGET.old-$(date +%Y%m%d%H%M%S)"
    mv "$TARGET" "$backup_path"
    BACKUP="$backup_path"
fi

mv "$EXTRACTED" "$TARGET"
if [ -n "$SAVED_MASTER" ]; then
    mkdir -p "$(dirname "$TARGET/$DATA_REL")"
    cp "$SAVED_MASTER" "$TARGET/$DATA_REL"
    ok "Restored your master list."
fi
if [ -n "$BACKUP" ]; then
    old="$BACKUP"
    BACKUP=""
    if rm -rf "$old"; then
        ok "Removed the old version."
    else
        note "Could not fully remove the old version. You can delete $old yourself."
    fi
fi
ok "Program files are in place."

# -- 4. Finish ----------------------------------------------------------------
step 4 4 "Finishing up"
rm -rf "$TMP_DIR"
TMP_DIR=""
ok "Cleaned up temporary files."

if [ -n "$IS_UPDATE" ]; then VERB="Updated"; else VERB="Installed"; fi
printf '\n'
rule
printf '\n'
printf '     %s%s - ready to go!%s\n' "$IPA_GREEN" "$VERB" "$RESET"
printf '\n'
printf '     %sInstalled in: %s %s\n' "$DIM" "$RESET" "$TARGET"
printf '     %sOpen it later:%s bash "%s/run.sh"\n' "$DIM" "$RESET" "$TARGET"
printf '     %sUpdate later: %s paste the same line into a terminal again:\n' "$DIM" "$RESET"
printf '                    %s\n' "$ONE_LINER"
printf '\n'
printf '     %s%s%s\n' "$YELLOW" "The first start sets up the program. That takes a few minutes, once." "$RESET"
printf '\n'
rule
printf '\n'

# The launcher clears the screen, so let the summary be read first.
if [ -z "${FPR_INSTALL_DIR:-}" ] && has_tty; then
    printf '     Press Enter to start the app ' > /dev/tty
    read -r _ < /dev/tty || true
fi

# -- Launch -------------------------------------------------------------------
# run.sh resolves its own location; use bash so no +x bit is needed. exec hands
# the terminal over, so stopping the app does not run this script's traps.
trap - EXIT ERR
cd "$TARGET"
exec bash "$TARGET/run.sh"
