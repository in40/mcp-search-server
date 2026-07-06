import asyncio
import base64
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

import aiohttp
import requests as http_requests
import trafilatura
import urllib3

from .config import (
    BRAVE_SEARCH_API_KEY, YANDEX_SEARCH_API_KEY, YANDEX_FOLDER_ID,
    YANDEX_SEARCH_TYPE, SEARCH_PROVIDER, USER_AGENTS, WAF_INDICATORS
)
from .log import add_log, next_request_id

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class SearchHandler:
    def __init__(self):
        self.version = "2.2.0"
        self.user_agents = USER_AGENTS

    async def _fetch_url_async(self, url: str, session: aiohttp.ClientSession, user_agents: List[str]) -> Dict:
        headers = {
            "User-Agent": user_agents[hash(url) % len(user_agents)],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15), ssl=True) as resp:
                if resp.status != 200:
                    return {"success": False, "error": f"HTTP {resp.status}"}

                content = await resp.read()
                extracted = trafilatura.extract(
                    content,
                    include_comments=False,
                    include_tables=True,
                    include_images=False,
                    include_formatting=True
                )

                metadata = trafilatura.extract_metadata(content)
                metadata_dict = {}
                if metadata:
                    metadata_dict = {
                        "title": getattr(metadata, 'title', None),
                        "author": getattr(metadata, 'author', None),
                        "description": getattr(metadata, 'description', None),
                        "site_name": getattr(metadata, 'sitename', None)
                    }

                return {
                    "success": True,
                    "content": extracted or "",
                    "metadata": metadata_dict,
                    "content_length": len(extracted) if extracted else 0
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def internet_search(self, query: str, count: int = 5, fetch_content: bool = False,
                        client: str = "unknown", provider: Optional[str] = None) -> Dict:
        provider = (provider or SEARCH_PROVIDER).lower()

        if provider == "yandex":
            return self._yandex_search(query, count, client, provider)

        request_id = next_request_id()

        start_time = time.time()

        original_query = query
        query = query.strip()
        query = query.strip('"\'')

        if len(query) > 400:
            truncated = query[:400].rsplit(' ', 1)[0]
            query = truncated

        request_data = {"query": original_query, "count": count, "fetch_content": fetch_content}

        if query != original_query:
            print(f"Query sanitized: {len(original_query)} -> {len(query)} chars")

        try:
            headers = {
                "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
                "Accept": "application/json",
                "User-Agent": self.user_agents[hash(query) % len(self.user_agents)]
            }

            params = {"q": query, "count": min(count, 20)}

            response = http_requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=30
            )

            brave_response = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body_preview": response.text[:500] if response.text else None
            }

            if response.status_code != 200:
                duration_ms = int((time.time() - start_time) * 1000)
                error_msg = f"Brave Search API error: HTTP {response.status_code}"
                add_log(request_id=request_id, request_type="search", client=client,
                        request_data=request_data, response_data=brave_response, error=error_msg)
                return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}

            data = response.json()
            web_results = data.get("web", {}).get("results", [])

            results = []
            for r in web_results[:count]:
                results.append({
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "date": r.get("age", "") or r.get("published_date", "") or "",
                })

            duration_ms = int((time.time() - start_time) * 1000)
            add_log(request_id=request_id, request_type="search", client=client,
                    request_data=request_data, response_data={
                        "results_count": len(results),
                        "results": results,
                        "duration_ms": duration_ms
                    }, error=None)

            return {
                "success": True,
                "results": results,
                "query": query,
                "provider": provider,
                "pages_fetched": 0,
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Brave search error: {str(e)}"
            add_log(request_id=request_id, request_type="search", client=client,
                    request_data=request_data, error=error_msg)
            return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}

    def _yandex_search(self, query: str, count: int, client: str, provider: str = "yandex") -> Dict:
        request_id = next_request_id()

        start_time = time.time()
        request_data = {"query": query, "count": count, "provider": "yandex"}

        if not YANDEX_SEARCH_API_KEY or not YANDEX_FOLDER_ID:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = "Yandex Search API key or folder ID not configured"
            add_log(request_id=request_id, request_type="search", client=client,
                    request_data=request_data, error=error_msg)
            return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}

        try:
            body = {
                "query": {
                    "searchType": YANDEX_SEARCH_TYPE,
                    "queryText": query,
                },
                "groupSpec": {
                    "groupsOnPage": min(count, 100),
                    "groupMode": "GROUP_MODE_FLAT",
                    "docsInGroup": 1,
                },
                "maxPassages": 4,
                "folderId": YANDEX_FOLDER_ID,
                "responseFormat": "FORMAT_XML",
            }
            headers = {
                "Authorization": f"Api-Key {YANDEX_SEARCH_API_KEY}",
                "Content-Type": "application/json",
            }

            yandex_start = time.time()
            try:
                response = http_requests.post(
                    "https://searchapi.api.cloud.yandex.net/v2/web/search",
                    json=body, headers=headers, timeout=30
                )
            except (http_requests.exceptions.ConnectTimeout, http_requests.exceptions.ReadTimeout) as e:
                yandex_ms = int((time.time() - yandex_start) * 1000)
                duration_ms = int((time.time() - start_time) * 1000)
                error_msg = f"Yandex API timeout ({type(e).__name__}) after {yandex_ms}ms"
                add_log(request_id=request_id, request_type="search", client=client,
                        request_data=request_data, error=error_msg)
                return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}
            except http_requests.exceptions.ConnectionError as e:
                yandex_ms = int((time.time() - yandex_start) * 1000)
                duration_ms = int((time.time() - start_time) * 1000)
                error_msg = f"Yandex API connection error after {yandex_ms}ms: {str(e)[:200]}"
                add_log(request_id=request_id, request_type="search", client=client,
                        request_data=request_data, error=error_msg)
                return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}

            yandex_ms = int((time.time() - yandex_start) * 1000)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code != 200:
                body_preview = response.text[:500] if response.text else ""
                error_msg = f"Yandex API error: HTTP {response.status_code} ({yandex_ms}ms)"
                add_log(request_id=request_id, request_type="search", client=client,
                        request_data=request_data,
                        response_data={"status_code": response.status_code, "body_preview": body_preview, "yandex_ms": yandex_ms},
                        error=error_msg)
                return {"success": False, "error": f"{error_msg}: {body_preview[:200]}", "provider": provider, "duration_ms": duration_ms}

            data = response.json()
            raw_b64 = data.get("rawData", "")
            if not raw_b64:
                duration_ms = int((time.time() - start_time) * 1000)
                add_log(request_id=request_id, request_type="search", client=client,
                        request_data=request_data, error="Empty Yandex response")
                return {"success": True, "results": [], "query": query, "provider": provider,
                        "pages_fetched": 0, "duration_ms": duration_ms}

            xml_bytes = base64.b64decode(raw_b64)
            root = ET.fromstring(xml_bytes)

            def _full_text(el):
                return "".join(el.itertext()) if el is not None else ""

            results = []
            for doc in root.findall(".//doc"):
                results.append({
                    "title": _full_text(doc.find("title")),
                    "url": _full_text(doc.find("url")),
                    "description": _full_text(doc.find("passages")),
                    "date": "",
                })

            results = results[:count]
            duration_ms = int((time.time() - start_time) * 1000)
            add_log(request_id=request_id, request_type="search", client=client,
                    request_data=request_data, response_data={
                        "results_count": len(results),
                        "results": results,
                        "yandex_ms": yandex_ms,
                    }, error=None)

            return {
                "success": True,
                "results": results,
                "query": query,
                "provider": provider,
                "pages_fetched": 0,
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            exc_type = type(e).__name__
            error_msg = f"Yandex search error [{exc_type}] after {duration_ms}ms: {str(e)[:300]}"
            add_log(request_id=request_id, request_type="search", client=client,
                    request_data=request_data, response_data={"exception_type": exc_type, "duration_ms": duration_ms},
                    error=error_msg)
            return {"success": False, "error": error_msg, "provider": provider, "duration_ms": duration_ms}

    def _is_bot_challenge(self, response) -> bool:
        if response.status_code not in (401, 403, 429):
            return False
        try:
            body = response.text[:2000].lower()
        except Exception:
            return False
        return any(i in body for i in WAF_INDICATORS)

    class _CurlResponse:
        __slots__ = ('status_code', 'content', 'text')
        def __init__(self, status_code: int, content: bytes):
            self.status_code = status_code
            self.content = content
            self.text = content.decode('utf-8', errors='replace')

    def _fetch_with_browser(self, url: str, timeout: int = 30) -> Dict:
        if not HAS_PLAYWRIGHT:
            return {"success": False, "error": "Playwright not available"}
        user_agent = self.user_agents[hash(url) % len(self.user_agents)]
        playwright = None
        browser = None
        context = None
        page = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1920, "height": 1080},
                locale="ru-RU",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            html = page.content()
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_formatting=True,
            )
            return {
                "success": True,
                "content": extracted or "",
                "content_length": len(extracted) if extracted else 0,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    playwright.stop()
                except Exception:
                    pass

    def _get_wiki_from_mirror(self, url: str) -> Optional[Dict]:
        m = re.match(
            r'^https?://([a-z]+)\.(?:ruwiki\.ru|wikipedia\.org)/wiki/(.+)$',
            url
        )
        if not m:
            return None
        lang = m.group(1)
        title = unquote(m.group(2))
        api_url = f"https://{lang}.wikipedia.org/w/api.php"
        headers = {
            "User-Agent": "MCP-Search-Server/2.0 (bot-bypass-fallback; +https://github.com/in40/mcp-search-server)",
        }
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "titles": title,
                "explaintext": "1",
                "format": "json",
            }
            resp = http_requests.get(api_url, params=params, timeout=10, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    continue
                extract = page_data.get("extract", "")
                if extract:
                    return {
                        "success": True,
                        "content": extract,
                        "content_length": len(extract),
                    }
            params = {
                "action": "query",
                "prop": "revisions",
                "titles": title,
                "rvprop": "content",
                "format": "json",
            }
            resp = http_requests.get(api_url, params=params, timeout=10, headers=headers)
            if resp.status_code != 200:
                return None
            data = resp.json()
            pages = data.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    continue
                revisions = page_data.get("revisions", [])
                if revisions:
                    content = revisions[0].get("*", "")
                    if content:
                        return {
                            "success": True,
                            "content": content,
                            "content_length": len(content),
                        }
            return None
        except Exception:
            return None

    def fetch_url(self, url: str, client: str = "unknown") -> Dict:
        request_id = next_request_id()

        if isinstance(url, str) and ("{'value':" in url or "{'url':" in url):
            try:
                url = url.replace("'", '"')
                parsed = json.loads(url)
                url = parsed.get("value") or parsed.get("url") or url
            except Exception:
                pass

        start_time = time.time()
        request_data = {"url": url}

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }

            verify_ssl = True
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    response = http_requests.get(url, headers=headers, timeout=10, verify=verify_ssl)
                    break
                except http_requests.exceptions.SSLError:
                    if verify_ssl:
                        verify_ssl = False
                        continue
                    raise
                except (http_requests.exceptions.ConnectionError, ConnectionResetError) as e:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    raise e

            if response.status_code != 200 and self._is_bot_challenge(response):
                try:
                    import subprocess as _subprocess
                    curl_cmd = [
                        'curl', '-sS', '-L', '--http2',
                        '-o', '-', '-w', '\n%{http_code}',
                        url,
                        '-A', headers.get('User-Agent', ''),
                        '-m', '15', '--connect-timeout', '10',
                    ]
                    if not verify_ssl:
                        curl_cmd.append('-k')
                    proc = _subprocess.run(curl_cmd, capture_output=True, timeout=25)
                    if proc.returncode == 0 and proc.stdout:
                        output = proc.stdout.decode('utf-8', errors='replace')
                        parts = output.rsplit('\n', 1)
                        body_str = parts[0] if len(parts) > 1 else ''
                        status_str = parts[-1].strip()
                        if status_str.isdigit() and int(status_str) == 200:
                            body_bytes = body_str.encode('utf-8')
                            response = self._CurlResponse(int(status_str), body_bytes)
                except Exception:
                    pass

            if response.status_code != 200:
                try:
                    pw_result = self._fetch_with_browser(url)
                    if pw_result.get("success"):
                        body_bytes = pw_result["content"].encode('utf-8')
                        response = self._CurlResponse(200, body_bytes)
                except Exception:
                    pass

            if response.status_code != 200:
                try:
                    wiki_result = self._get_wiki_from_mirror(url)
                    if wiki_result and wiki_result.get("success"):
                        body_bytes = wiki_result["content"].encode('utf-8')
                        response = self._CurlResponse(200, body_bytes)
                except Exception:
                    pass

            if response.status_code != 200:
                duration_ms = int((time.time() - start_time) * 1000)

                try:
                    error_text = response.text
                    if len(error_text) > 100:
                        import re
                        clean_text = re.sub(r'<[^>]+>', ' ', error_text[:3000])
                        clean_text = ' '.join(clean_text.split())
                        if len(clean_text) > 50:
                            from .utils import sanitize_text
                            sanitized_content = sanitize_text(f"[HTTP {response.status_code}] {clean_text[:2000]}", max_length=2000)
                            return {
                                "success": True,
                                "url": url,
                                "content": sanitized_content,
                                "metadata": {},
                                "duration_ms": duration_ms
                            }
                except Exception:
                    pass

                error_messages = {
                    401: "Доступ запрещен (требуется авторизация)",
                    403: "Доступ запрещен",
                    404: "Страница не найдена",
                    408: "Тайм-ут соединения",
                    429: "Слишком много запросов",
                    500: "Внутренняя ошибка сервера",
                    502: "Ошибка шлюза",
                    503: "Сервис временно недоступен",
                    504: "Тайм-ут шлюза"
                }

                error_msg = error_messages.get(response.status_code, f"Ошибка HTTP {response.status_code}")

                add_log(
                    request_id=request_id,
                    request_type="fetch",
                    client=client,
                    request_data=request_data,
                    response_data={
                        "status_code": response.status_code,
                        "content_length": len(response.content),
                        "metadata": {},
                        "content": None
                    },
                    error=error_msg
                )

                from .utils import sanitize_text
                sanitized_content = sanitize_text(f"\u26a0\ufe0f {error_msg}: {url} (\u0441\u0430\u0439\u0442 \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0430\u0432\u0442\u043e\u0440\u0438\u0437\u0430\u0446\u0438\u044e \u0438\u043b\u0438 \u0431\u043b\u043e\u043a\u0438\u0440\u0443\u0435\u0442 \u0431\u043e\u0442\u043e\u0432)", max_length=2000)
                if not sanitized_content:
                    sanitized_content = f"[Error fetching: {url}]"
                return {
                    "success": True,
                    "url": url,
                    "content": sanitized_content,
                    "metadata": {},
                    "duration_ms": duration_ms
                }

            extracted = trafilatura.extract(
                response.content,
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_formatting=True,
                favor_precision=True
            )

            if not extracted or len(extracted.strip()) < 50:
                extracted = trafilatura.extract(
                    response.content,
                    include_comments=False,
                    include_tables=False,
                    include_images=False,
                    include_formatting=False,
                    favor_precision=False
                )

            metadata = trafilatura.extract_metadata(response.content)

            content_length = len(extracted) if extracted else 0

            metadata_dict = {}
            if metadata:
                metadata_dict = {
                    "title": getattr(metadata, 'title', None),
                    "author": getattr(metadata, 'author', None),
                    "description": getattr(metadata, 'description', None),
                    "site_name": getattr(metadata, 'sitename', None)
                }

            if not extracted or len(extracted.strip()) < 50:
                wiki_result = self._get_wiki_from_mirror(url)
                if wiki_result and wiki_result.get("success"):
                    extracted = wiki_result["content"]
                    content_length = len(extracted)

            if not extracted or len(extracted.strip()) < 50:
                js_heavy_domains = ['vk.com', 'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com']
                is_js_heavy = any(domain in url for domain in js_heavy_domains)

                if not is_js_heavy:
                    pw_result = self._fetch_with_browser(url)
                    if pw_result.get("success") and pw_result.get("content"):
                        extracted = pw_result["content"]
                        content_length = len(extracted)

            if not extracted or len(extracted.strip()) < 50:
                js_heavy_domains = ['vk.com', 'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com']
                is_js_heavy = any(domain in url for domain in js_heavy_domains)

                if is_js_heavy:
                    extracted = f"[Content requires JavaScript: {url}]"
                    content_length = len(extracted)
                else:
                    try:
                        raw_text = response.text[:5000]
                        if len(raw_text) > 0:
                            extracted = f"[Content requires JavaScript: {url}]"
                            content_length = len(extracted)
                    except Exception:
                        pass

            from .utils import sanitize_text
            extracted = sanitize_text(extracted or "", max_length=10000)
            content_length = len(extracted) if extracted else 0

            duration_ms = int((time.time() - start_time) * 1000)
            add_log(
                request_id=request_id,
                request_type="fetch",
                client=client,
                request_data=request_data,
                response_data={
                    "status_code": response.status_code,
                    "content_length": content_length,
                    "metadata": metadata_dict,
                    "content": sanitize_text(extracted[:2000]) if extracted else None
                },
                error=None
            )

            content = extracted if extracted else f"[No content extracted from {url}]"
            return {
                "success": True,
                "url": url,
                "content": content,
                "metadata": metadata_dict,
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_detail = str(e)[:500] if str(e) else "Unknown error"
            from .utils import sanitize_text
            error_msg = sanitize_text(f"\u26a0\ufe0f \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u0430\u043d\u043d\u044b\u0435 \u0441 \u0441\u0430\u0439\u0442\u0430: {url}\n\n\u041f\u0440\u0438\u0447\u0438\u043d\u0430: {error_detail}", max_length=2000)

            add_log(
                request_id=request_id,
                request_type="fetch",
                client=client,
                request_data=request_data,
                response_data={
                    "url": url,
                    "status_code": None,
                    "content_length": 0,
                    "metadata": {},
                    "content": error_msg
                },
                error=error_msg
            )

            if not error_msg:
                error_msg = f"[Error fetching: {url}]"
            return {
                "success": True,
                "url": url,
                "content": error_msg,
                "metadata": {},
                "duration_ms": duration_ms
            }
