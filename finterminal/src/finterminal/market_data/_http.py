from __future__ import annotations
import time
import requests

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
_RATE_LIMIT_SECONDS = 1.0
_BACKOFF_SECONDS = 5.0
_TIMEOUT = 20

class Http404(Exception): ...
class Http429(Exception): ...

_session: requests.Session | None = None

def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_HEADERS)
        try:
            s.get("https://www.nseindia.com", timeout=_TIMEOUT)  # cookie warm-up
        except Exception:
            pass
        _session = s
    return _session

def fetch(url: str, *, _attempt: int = 0) -> bytes:
    session = _get_session()
    time.sleep(_RATE_LIMIT_SECONDS)
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                        cookies=session.cookies)
    if resp.status_code == 200:
        return resp.content
    if resp.status_code == 404:
        raise Http404(url)
    if resp.status_code == 429:
        if _attempt == 0:
            time.sleep(_BACKOFF_SECONDS)
            return fetch(url, _attempt=1)
        raise Http429(url)
    raise RuntimeError(f"unexpected status {resp.status_code} for {url}")
