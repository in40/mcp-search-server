import json
import os
from http.server import BaseHTTPRequestHandler

from ..config import API_KEYS_PATH, DASHBOARD_THEME
from ..log import get_logs, get_stats


def _load_templates():
    import importlib.resources as res
    templates = {}
    for name in ("dashboard_blue.html", "dashboard_orange.html"):
        try:
            templates[name] = res.files("mcp_search_server.templates").joinpath(name).read_text()
        except (ModuleNotFoundError, TypeError, FileNotFoundError):
            p = os.path.join(os.path.dirname(__file__), "..", "templates", name)
            with open(p) as f:
                templates[name] = f.read()
    return templates


_TEMPLATES = _load_templates()


class DashboardHandler(BaseHTTPRequestHandler):
    timeout = 30
    max_body_size = 1 * 1024 * 1024

    def __init__(self, search_handler=None, *args, **kwargs):
        self.search_handler = search_handler
        super().__init__(*args, **kwargs)

    def handle_timeout(self):
        try:
            self.send_response(408)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Request timeout"}).encode())
        except Exception:
            pass

    def _load_api_keys(self):
        try:
            with open(API_KEYS_PATH) as f:
                return json.load(f).get("keys", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _validate_api_key(self):
        key = self.headers.get("X-API-Key", "")
        keys = self._load_api_keys()
        if not key or key not in keys:
            self._send_json({"error": "Unauthorized: invalid or missing X-API-Key"}, 401)
            return False
        return True

    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.end_headers()

    def do_POST(self):
        if not self._validate_api_key():
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self.max_body_size:
            self._send_json({"error": "Request too large"}, 413)
            return
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        if self.path == "/api/search":
            query = data.get("query", "")
            count = data.get("count", 5)
            if not query:
                self._send_json({"error": "query is required"}, 400)
                return
            result = self.search_handler.internet_search(query=query, count=count, client="rest-api")
            if result.get("success"):
                self._send_json(result.get("results", []))
            else:
                self._send_json({"error": result.get("error", "search failed")}, 502)

        elif self.path == "/api/fetch":
            url = data.get("url", "")
            if not url:
                self._send_json({"error": "url is required"}, 400)
                return
            result = self.search_handler.fetch_url(url=url, client="rest-api")
            self._send_json(result)

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            return

        elif self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(get_stats()).encode())
            return

        elif self.path.startswith("/logs"):
            params = {}
            if "?" in self.path:
                query_string = self.path.split("?", 1)[1]
                for param in query_string.split("&"):
                    if "=" in param:
                        k, v = param.split("=", 1)
                        params[k] = v

            logs = get_logs(
                since=params.get("since"),
                log_type=params.get("type"),
                limit=int(params.get("limit", 100))
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"logs": logs, "count": len(logs)}).encode())
            return

        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = _TEMPLATES.get("dashboard_orange.html") if DASHBOARD_THEME == "orange" else _TEMPLATES.get("dashboard_blue.html", "")
            self.wfile.write(html.encode())
            return

        else:
            self.send_response(404)
            self.end_headers()
