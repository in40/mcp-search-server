import json
from http.server import BaseHTTPRequestHandler

from ..config import API_KEYS_PATH


class MCPHandler(BaseHTTPRequestHandler):
    timeout = 30
    max_body_size = 1 * 1024 * 1024

    def __init__(self, search_handler, *args, **kwargs):
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
            self._send_error(-32001, "Unauthorized: invalid or missing X-API-Key")
            return False
        return True

    def _send_error(self, code, message, request_id=None):
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message}
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if not self._validate_api_key():
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self.max_body_size:
            self._send_error(-32002, "Request too large")
            return
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body)
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            client = f"{self.client_address[0]}:{self.client_address[1]}"

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mcp-search-server", "version": self.search_handler.version}
                    }
                }

            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "internet_search",
                                "description": "Search the internet using Yandex Search. Returns titles, URLs, descriptions, and full page content in markdown format.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string", "description": "The search query"},
                                        "count": {"type": "integer", "description": "Number of results (default: 5, max: 20)", "default": 5}
                                    },
                                    "required": ["query"]
                                }
                            },
                            {
                                "name": "fetch_url",
                                "description": "Fetch a web page and return its content as markdown with metadata.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "url": {"type": "string", "description": "The URL to fetch"}
                                    },
                                    "required": ["url"]
                                }
                            }
                        ]
                    }
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})

                if tool_name == "internet_search":
                    result = self.search_handler.internet_search(
                        query=tool_args.get("query", ""),
                        count=tool_args.get("count", 10),
                        fetch_content=tool_args.get("fetch_content", True),
                        provider=tool_args.get("provider", None),
                        client=client
                    )
                    if not result.get("success", True):
                        content_items = [{"type": "text", "text": json.dumps({"error": result.get("error", "unknown error")}, ensure_ascii=False)}]
                    else:
                        results = result.get("results", [])
                        if results:
                            content_items = []
                            for r in results:
                                flat = {
                                    "url": r.get("url", ""),
                                    "title": r.get("title", ""),
                                    "description": r.get("description", ""),
                                    "date": r.get("date", ""),
                                }
                                if r.get("content"):
                                    flat["content"] = r["content"]
                                content_items.append({"type": "text", "text": json.dumps(flat, ensure_ascii=False)})
                        else:
                            content_items = [{"type": "text", "text": json.dumps({"error": "no_results"}, ensure_ascii=False)}]
                elif tool_name == "fetch_url":
                    result = self.search_handler.fetch_url(
                        url=tool_args.get("url", ""),
                        client=client
                    )
                    content_items = [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                else:
                    content_items = [{"type": "text", "text": json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)}]

                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content_items
                    }
                }

            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if "request" in locals() else None,
                "error": {"code": -32700, "message": str(e)}
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
