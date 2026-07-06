#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$REPO_DIR/dist"
BUNDLE_DIR="$OUT_DIR/offline"
WHEELS_DIR="$BUNDLE_DIR/wheels"

echo "=== Building offline bundle for mcp-search-server ==="

# Clean
rm -rf "$BUNDLE_DIR"
mkdir -p "$WHEELS_DIR"

# 1. Build package wheel
echo "[1/3] Building package wheel..."
python3 -m pip wheel "$REPO_DIR" --wheel-dir="$WHEELS_DIR" --no-deps --quiet

# 2. Download all dependency wheels
echo "[2/3] Downloading dependency wheels..."
python3 -m pip download \
    --only-binary=:all: \
    --dest="$WHEELS_DIR" \
    --requirement "$REPO_DIR/requirements.txt" \
    --quiet

# 3. Copy config files
echo "[3/3] Copying config files..."
cp "$REPO_DIR/api_keys.json.example" "$BUNDLE_DIR/"
cp "$REPO_DIR/requirements.txt" "$BUNDLE_DIR/"
cp "$REPO_DIR/README.md" "$BUNDLE_DIR/"
cp "$SCRIPT_DIR/../dist/offline/install.sh" "$BUNDLE_DIR/" 2>/dev/null || cat > "$BUNDLE_DIR/install.sh" << 'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=$(command -v python3 || command -v python)
if [ "${1:-}" = "--venv" ] || [ "${1:-}" = "-v" ]; then
    VENV_DIR="${2:-./venv}"
    "$PYTHON" -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    PYTHON="$VENV_DIR/bin/python"
fi
"$PYTHON" -m pip install --no-index --find-links="$SCRIPT_DIR/wheels" "$SCRIPT_DIR/wheels/mcp_search_server"*.whl
echo "Install complete. Run: mcp-search-server"
INSTALL
chmod +x "$BUNDLE_DIR/install.sh"

# 4. Create tar.gz
echo "Creating archive..."
cd "$OUT_DIR"
tar czf mcp-search-server-offline.tar.gz offline/
rm -rf "$BUNDLE_DIR"

ls -lh "$OUT_DIR/mcp-search-server-offline.tar.gz"
echo "=== Done ==="
