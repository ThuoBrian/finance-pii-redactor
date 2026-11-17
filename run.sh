#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -- Colours & styling --------------------------------------------------------
RESET='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'
CYAN='\033[1;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
WHITE='\033[1;37m'
# IPA brand colour (primary green #49ac57) - 24-bit truecolor
IPA_GREEN='\033[38;2;73;172;87m'

spinner() {
    local pid=$1
    local message=$2
    local chars='|/-\'
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r      %s %s" "${IPA_GREEN}${chars:i:1}${RESET}" "$message"
        i=$(((i + 1) % 4))
        sleep 0.1
    done
    printf "\r%*s\r" "$((${#message} + 12))" ""
}

print_banner() {
    clear 2>/dev/null || true
    echo ""
    echo -e " ${IPA_GREEN}====================================================================${RESET}"
    echo ""
    echo -e "     ${BOLD}${WHITE}FINANCE PII REDACTOR${RESET}"
    echo -e "     ${DIM}Removes names and organizations from your Excel, PDF and Word files.${RESET}"
    echo -e "     ${BOLD}${IPA_GREEN}Runs 100% on your computer - nothing is ever uploaded.${RESET}"
    echo ""
    echo -e " ${IPA_GREEN}====================================================================${RESET}"
    echo ""
    echo -e "    ${DIM}Getting things ready. This usually takes only a few seconds.${RESET}"
    echo -e "    ${DIM}The first time you run it, setup can take a few minutes.${RESET}"
    echo ""
}

print_step() {
    echo ""
    echo -e "   ${IPA_GREEN}[ Step $1 of $2 ]${RESET} ${BOLD}$3${RESET}"
}

print_ok() {
    echo -e "      ${IPA_GREEN}[OK]${RESET} $1"
}

print_info() {
    echo -e "      ${DIM}${WHITE}[INFO]${RESET} $1"
}

print_error() {
    echo ""
    echo -e "      ${RED}[PROBLEM]${RESET} $1"
}

print_hint() {
    echo -e "      ${DIM}$1${RESET}"
}

print_ready() {
    echo ""
    echo -e " ${IPA_GREEN}====================================================================${RESET}"
    echo ""
    echo -e "     ${BOLD}${IPA_GREEN}All set - starting the app now!${RESET}"
    echo ""
    echo -e "     ${WHITE}Your web browser will open automatically in a moment.${RESET}"
    echo -e "     ${DIM}If it does not, open this address:${RESET} ${IPA_GREEN}http://127.0.0.1:8501${RESET}"
    echo ""
    echo -e "     ${YELLOW}Keep this window open while you use the app.${RESET}"
    echo -e "     ${DIM}When you are finished, click \"Close the app\" in the sidebar.${RESET}"
    echo ""
    echo -e " ${IPA_GREEN}====================================================================${RESET}"
    echo ""
}

print_banner

# onnxruntime (used for reading scanned pages) publishes no build for Intel
# Macs, so `uv sync` would fail with a confusing error. Stop here instead.
if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "x86_64" ]; then
    print_error "This Mac has an Intel processor, which the tool does not support."
    print_hint "It runs on Apple Silicon Macs (M1 or newer), Windows and Linux."
    exit 1
fi

# -- 1. Install uv if not already present -------------------------------------
print_step 1 2 "Checking the setup helper"
if ! command -v uv >/dev/null 2>&1; then
    print_info "First-time setup: installing a small helper (one-time)."
    (curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1) &
    spinner $! "Installing setup helper, please wait..."
    wait $! || {
        print_error "Setup helper could not be installed."
        print_hint "Please check your internet connection, then run this again."
        exit 1
    }
    export PATH="$HOME/.local/bin:$PATH"
    print_ok "Setup helper installed."
else
    print_ok "Setup helper is ready."
fi

# -- 2. Create virtual environment and install dependencies -------------------
print_step 2 2 "Preparing the program"
# Set up on first run, and again whenever uv.lock changed since the last
# setup (an update copied over an existing folder, or a git pull). A copy of
# uv.lock kept inside .venv records what was last installed.
SYNCED="$APP_DIR/.venv/.synced-uv.lock"
NEEDSYNC=""
if [ ! -d "$APP_DIR/.venv" ]; then
    NEEDSYNC="first"
elif ! cmp -s "$APP_DIR/uv.lock" "$SYNCED"; then
    NEEDSYNC="update"
fi
if [ -n "$NEEDSYNC" ]; then
    if [ "$NEEDSYNC" = "first" ]; then
        print_info "First-time setup: installing the program and language model (one-time)."
        WAIT_MSG="Large download, this can take a few minutes..."
    else
        print_info "Installing updated components for this version (one-time)."
        WAIT_MSG="This can take a minute..."
    fi
    (uv sync --python 3.12 --project "$APP_DIR" >/tmp/finance-redact-setup.log 2>&1) &
    spinner $! "$WAIT_MSG"
    wait $! || {
        print_error "The program could not be set up."
        print_hint "Please check your internet connection, then run this again."
        echo ""
        echo "Setup log:"
        cat /tmp/finance-redact-setup.log 2>/dev/null || true
        exit 1
    }
    cp "$APP_DIR/uv.lock" "$SYNCED"
    print_ok "Program is ready."
else
    print_ok "Program is ready."
fi

# -- 3. Launch the app --------------------------------------------------------
print_ready
"$APP_DIR/.venv/bin/python" "$APP_DIR/app.py"
