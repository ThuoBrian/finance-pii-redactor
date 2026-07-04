#!/usr/bin/env bash
set -euo pipefail

# package.sh — create a clean, shareable zip of the Finance PII Redactor.
#
# Usage:
#   ./package.sh
#
# Output:
#   ../finance-pii-redactor.zip

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$(dirname "$APP_DIR")"
OUTPUT_NAME="finance-pii-redactor.zip"
OUTPUT_PATH="$OUTPUT_DIR/$OUTPUT_NAME"

echo "Packaging Finance PII Redactor for sharing..."

# Remove any previous package.
if [ -f "$OUTPUT_PATH" ]; then
    echo "Removing existing $OUTPUT_NAME..."
    rm "$OUTPUT_PATH"
fi

# Build the zip, excluding runtime/cache artifacts.
(
    cd "$OUTPUT_DIR"
    zip -r "$OUTPUT_NAME" "$(basename "$APP_DIR")" \
        -x "*/.venv/*" \
        -x "*/__pycache__/*" \
        -x "*/.DS_Store" \
        -x "*/.ruff_cache/*" \
        -x "*/.claude/*" \
        -x "*/_legacy/*" \
        -x "*.pyc"
)

echo ""
echo "Created: $OUTPUT_PATH"
echo ""
echo "Excluded: .venv, __pycache__, .DS_Store, .ruff_cache, .claude, _legacy, *.pyc"
echo "Recipient should run run.bat (Windows) or ./run.sh (macOS/Linux) after extracting."
