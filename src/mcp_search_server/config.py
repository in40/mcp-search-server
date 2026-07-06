import os
from pathlib import Path

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "CHANGE_ME_BRAVE_API_KEY")
YANDEX_SEARCH_API_KEY = os.getenv("YANDEX_SEARCH_API_KEY") or "CHANGE_ME_YANDEX_API_KEY"
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID") or "CHANGE_ME_YANDEX_FOLDER_ID"
YANDEX_SEARCH_TYPE = os.getenv("YANDEX_SEARCH_TYPE", "SEARCH_TYPE_COM")
SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "yandex")
PORT = int(os.getenv("PORT", 8090))
LOG_RETENTION_HOURS = int(os.getenv("LOG_RETENTION_HOURS", 24))
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 8091))
API_KEYS_PATH = os.getenv("API_KEYS_PATH", str(Path(__file__).parent.parent.parent / "api_keys.json"))

DASHBOARD_THEME = os.getenv("DASHBOARD_THEME", "")  # "orange" for v2 theme

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]

WAF_INDICATORS = [
    "qrator", "/__qrator/", "qauth.js",
    "cloudflare", "__cf_chl", "cf-ray",
    "incapsula", "visid_incap",
    "ddos-guard", "__ddg",
    "checking your browser", "just a moment",
    "/cdn-cgi/",
]

VERSION = "2.2.0"
