# MCP Search Server

MCP-compliant server providing web search (Yandex Search API) and URL fetching capabilities over JSON-RPC 2.0. Includes a built-in monitoring dashboard with live log feed and request statistics.

## Quick Start

```bash
# Install
pip install mcp-search-server

# With Playwright support (for JS-heavy sites):
pip install "mcp-search-server[playwright]"
playwright install --with-deps chromium
```

```bash
# Configure
export YANDEX_SEARCH_API_KEY="your-yandex-api-key"
export YANDEX_FOLDER_ID="your-yandex-folder-id"
export YANDEX_SEARCH_TYPE="SEARCH_TYPE_COM"  # or SEARCH_TYPE_RU for Russian results
```

```bash
# Run
mcp-search-server
```

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                   mcp-search-server                     │
│                                                        │
│  Port 8090: MCP JSON-RPC 2.0  |  Port 8091: Dashboard  │
│  ┌──────────────────────────┐ | ┌────────────────────┐ │
│  │  tools/list              │ | │  GET /  (HTML UI)  │ │
│  │  tools/call              │ | │  GET /health       │ │
│  │    - internet_search     │ | │  GET /stats        │ │
│  │    - fetch_url           │ | │  GET /logs         │ │
│  └──────────────────────────┘ | │  POST /api/search  │ │
│                                | │  POST /api/fetch   │ │
│  In-memory log ring buffer     | └────────────────────┘ │
│  (24h retention, auto-cleanup) |                        │
└────────────────────────────────────────────────────────┘
```

## Features

### Search (Yandex Cloud Search API)

- Primary search provider: Yandex Cloud Search API
- Fallback: Brave Search API (configurable via `SEARCH_PROVIDER`)
- Results include title, URL, description excerpts

### URL Fetch (`fetch_url`)

Multi-layered fallback system:

1. **requests** library with Chrome UA headers (primary)
2. **SSL fallback** - retries without cert verification for broken cert chains
3. **curl subprocess** - bypasses some WAF/bot challenges (QRATOR, Cloudflare)
4. **Playwright/Chromium** - headless browser for JS-heavy sites
5. **Wikipedia API** - direct API for QRATOR-protected Wikipedia mirrors
6. Content extraction via **trafilatura** (HTML-to-Markdown)
7. Russian-language error messages for all failure modes

### Dashboard (Port 8091)

- Real-time stats: total requests, last-hour, errors, search vs fetch breakdown
- Live log feed with auto-refresh (5s interval)
- Per-request detail modal (full JSON)
- Yandex search tab with timing and results
- Themes: blue (default), orange (set `DASHBOARD_THEME=orange`)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `YANDEX_SEARCH_API_KEY` | Yes | *(placeholder)* | Yandex Cloud API key |
| `YANDEX_FOLDER_ID` | Yes | *(placeholder)* | Yandex Cloud folder ID |
| `YANDEX_SEARCH_TYPE` | No | `SEARCH_TYPE_COM` | `SEARCH_TYPE_RU` for Russian results |
| `SEARCH_PROVIDER` | No | `yandex` | `brave` to use Brave Search API |
| `BRAVE_SEARCH_API_KEY` | No | *(placeholder)* | Required if `SEARCH_PROVIDER=brave` |
| `PORT` | No | `8090` | MCP JSON-RPC server port |
| `DASHBOARD_PORT` | No | `8091` | Dashboard + REST API port |
| `LOG_RETENTION_HOURS` | No | `24` | Hours to keep request logs in memory |
| `API_KEYS_PATH` | No | `./api_keys.json` | Path to API keys file |
| `DASHBOARD_THEME` | No | *(none)* | Set to `orange` for orange theme |

## Authentication

Both MCP and Dashboard endpoints require `X-API-Key` header matching keys in `api_keys.json`:

```json
{
    "keys": {
        "your-api-key-here": "read-write"
    }
}
```

## MCP JSON-RPC API

### `initialize`

```json
{"jsonrpc": "2.0", "method": "initialize", "id": 1}
```

### `tools/list`

Returns two tools: `internet_search` and `fetch_url`.

### `tools/call`

#### internet_search

```json
{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 2,
    "params": {
        "name": "internet_search",
        "arguments": { "query": "MCP protocol", "count": 5 }
    }
}
```

#### fetch_url

```json
{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "id": 3,
    "params": {
        "name": "fetch_url",
        "arguments": { "url": "https://example.com" }
    }
}
```

## REST API (Dashboard Port)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | No | Health check |
| `GET` | `/stats` | X-API-Key | Aggregated statistics |
| `GET` | `/logs?type=&limit=` | X-API-Key | Request logs |
| `GET` | `/` | X-API-Key | Dashboard HTML UI |
| `POST` | `/api/search` | X-API-Key | JSON: `{"query": "...", "count": 5}` |
| `POST` | `/api/fetch` | X-API-Key | JSON: `{"url": "..."}` |

## Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt1-dev libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY src/mcp_search_server/ /app/mcp_search_server/
COPY api_keys.json .
ENV API_KEYS_PATH=/app/api_keys.json

CMD ["python", "-m", "mcp_search_server"]
```

## Development

```bash
git clone https://github.com/in40/mcp-search-server.git
cd mcp-search-server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
playwright install --with-deps chromium
mcp-search-server
```

## License

Apache 2.0
