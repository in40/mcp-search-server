#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_DIR/dist"
BUNDLE_DIR="$OUT_DIR/offline"
WHEELS_DIR="$BUNDLE_DIR/wheels"
WITH_PLAYWRIGHT=false

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-playwright|-p) WITH_PLAYWRIGHT=true; shift ;;
        --help|-h) echo "Usage: $0 [--with-playwright]"; exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

echo "=== Building offline bundle for mcp-search-server ==="
echo "  Playwright: $WITH_PLAYWRIGHT"

# Clean
rm -rf "$BUNDLE_DIR"
mkdir -p "$WHEELS_DIR"

# 1. Build package wheel
echo "[1/4] Building package wheel..."
python3 -m pip wheel "$REPO_DIR" --wheel-dir="$WHEELS_DIR" --no-deps --quiet

# 2. Download core dependency wheels
echo "[2/4] Downloading dependency wheels..."
python3 -m pip download \
    --only-binary=:all: \
    --dest="$WHEELS_DIR" \
    --requirement "$REPO_DIR/requirements.txt" \
    --quiet

WHEEL_COUNT=$(ls "$WHEELS_DIR"/*.whl 2>/dev/null | wc -l)
echo "       $WHEEL_COUNT wheels downloaded"

# 3. Playwright + Chromium (optional)
if [ "$WITH_PLAYWRIGHT" = true ]; then
    echo "[3/4] Installing Playwright + Chromium..."
    python3 -m pip download --only-binary=:all: --dest="$WHEELS_DIR" playwright
    export PLAYWRIGHT_BROWSERS_PATH="$BUNDLE_DIR/browsers"
    # Install only what's needed for headless page rendering
    python3 -m playwright install chromium 2>&1 | grep -v '^|'
    # Remove ffmpeg (not needed - only used for video recording)
    rm -rf "$BUNDLE_DIR/browsers/ffmpeg-"*
    BROWSER_SIZE=$(du -sh "$BUNDLE_DIR/browsers" | cut -f1)
    echo "       Browsers size: $BROWSER_SIZE"
else
    echo "[3/4] Skipping Playwright (use --with-playwright to include)"
fi

# 4. Copy config files and create install script
echo "[4/4] Creating install script..."
cp "$REPO_DIR/api_keys.json.example" "$BUNDLE_DIR/"
cp "$REPO_DIR/requirements.txt" "$BUNDLE_DIR/"
cp "$REPO_DIR/README.md" "$BUNDLE_DIR/"

cat > "$BUNDLE_DIR/install.sh" << 'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3 not found"
    exit 1
fi

if [ "${1:-}" = "--venv" ] || [ "${1:-}" = "-v" ]; then
    VENV_DIR="${2:-./venv}"
    "$PYTHON" -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
fi

"$PYTHON" -m pip install --no-index --find-links="$SCRIPT_DIR/wheels" --quiet "$SCRIPT_DIR/wheels/mcp_search_server"*.whl

# Set up Playwright browsers path if bundled
if [ -d "$SCRIPT_DIR/browsers" ]; then
    mkdir -p "$HOME/.cache/ms-playwright"
    ln -sfn "$SCRIPT_DIR/browsers/chromium-"* "$HOME/.cache/ms-playwright/" 2>/dev/null || true
    echo "Playwright browsers linked to $HOME/.cache/ms-playwright/"
fi

echo ""
echo "=== Install complete ==="
echo ""
echo "To run:"
echo "  export YANDEX_SEARCH_API_KEY='your-key'"
echo "  export YANDEX_FOLDER_ID='your-folder-id'"
echo "  mcp-search-server"
INSTALL
chmod +x "$BUNDLE_DIR/install.sh"

# 5. Create tar.gz
echo ""
echo "Creating archive..."
cd "$OUT_DIR"
ARCHIVE="mcp-search-server-offline.tar.gz"
if [ "$WITH_PLAYWRIGHT" = true ]; then
    ARCHIVE="mcp-search-server-offline-full.tar.gz"
fi
tar czf "$ARCHIVE" offline/
rm -rf "$BUNDLE_DIR"

ls -lh "$OUT_DIR/$ARCHIVE"
echo "=== Done ==="
