import threading
from http.server import HTTPServer
from socketserver import ThreadingMixIn

from .config import PORT, DASHBOARD_PORT
from .handlers.dashboard import DashboardHandler
from .handlers.mcp import MCPHandler
from .search import SearchHandler


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False
    max_workers = 20
    _semaphore = threading.BoundedSemaphore(20)

    def process_request(self, request, client_address):
        self._semaphore.acquire()
        t = threading.Thread(target=self._process_with_release,
                             args=(request, client_address))
        t.daemon = self.daemon_threads
        t.start()

    def _process_with_release(self, request, client_address):
        try:
            self.process_request_thread(request, client_address)
        finally:
            self._semaphore.release()


def run_dashboard(search_handler):
    try:
        server = ThreadedHTTPServer(("0.0.0.0", DASHBOARD_PORT),
                            lambda *a, **kw: DashboardHandler(search_handler, *a, **kw))
        server.allow_reuse_address = True
        print(f"Dashboard running on http://0.0.0.0:{DASHBOARD_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"Dashboard failed to start: {e}", file=__import__('sys').stderr)


def run_mcp_server(handler):
    mcp_server = ThreadedHTTPServer(("0.0.0.0", PORT), lambda *args, **kwargs: MCPHandler(handler, *args, **kwargs))
    mcp_server.timeout = 30
    print(f"MCP Server running on port {PORT}")
    mcp_server.serve_forever()


def main():
    handler = SearchHandler()

    dashboard_thread = threading.Thread(target=run_dashboard, args=(handler,), daemon=True)
    dashboard_thread.start()

    run_mcp_server(handler)


if __name__ == "__main__":
    main()
