import threading
from datetime import datetime
from typing import Dict, List, Optional, Any

from .config import LOG_RETENTION_HOURS

request_logs: List[Dict[str, Any]] = []
request_lock = threading.Lock()
_request_counter = 0


def next_request_id() -> int:
    global _request_counter
    with request_lock:
        _request_counter += 1
        return _request_counter


def add_log(request_id: int, request_type: str, client: str, request_data: Dict,
            response_data: Optional[Dict] = None, error: Optional[str] = None):
    global request_counter
    with request_lock:
        entry = {
            "id": request_id,
            "timestamp": datetime.now().isoformat(),
            "type": request_type,
            "client": client,
            "request": request_data,
            "response": response_data,
            "error": error,
            "duration_ms": None
        }
        request_logs.append(entry)

        cutoff = datetime.now().timestamp() - (LOG_RETENTION_HOURS * 3600)
        request_logs[:] = [
            log for log in request_logs
            if datetime.fromisoformat(log["timestamp"]).timestamp() > cutoff
        ]


def get_logs(since: Optional[str] = None, log_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
    with request_lock:
        logs = request_logs.copy()

    if since:
        since_dt = datetime.fromisoformat(since)
        logs = [l for l in logs if datetime.fromisoformat(l["timestamp"]) > since_dt]

    if log_type:
        logs = [l for l in logs if l["type"] == log_type]

    return logs[-limit:]


def get_stats() -> Dict:
    with request_lock:
        logs = request_logs.copy()

    now = datetime.now()
    last_hour = now.timestamp() - 3600

    recent_logs = [
        l for l in logs
        if datetime.fromisoformat(l["timestamp"]).timestamp() > last_hour
    ]

    return {
        "total_requests": len(logs),
        "requests_last_hour": len(recent_logs),
        "search_requests": len([l for l in logs if l["type"] == "search"]),
        "fetch_requests": len([l for l in logs if l["type"] == "fetch"]),
        "errors": len([l for l in logs if l.get("error")]),
        "active_connections": 0
    }
