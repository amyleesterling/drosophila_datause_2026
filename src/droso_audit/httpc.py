"""Shared HTTP client: polite headers, retry/backoff, and on-disk caching."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import META_CACHE, USER_AGENT


class HostNotAllowed(RuntimeError):
    """Raised when the egress proxy blocks a host (sandbox allowlist)."""


_SESSION: Optional[requests.Session] = None


def session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        _SESSION = s
    return _SESSION


def _cache_path(key: str, suffix: str = ".json") -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return META_CACHE / f"{h}{suffix}"


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=2, min=2, max=16),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _request(method: str, url: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    resp = session().request(method, url, timeout=timeout, **kwargs)
    if resp.status_code == 403 and "host_not_allowed" in resp.headers.get("x-deny-reason", ""):
        raise HostNotAllowed(f"Egress proxy blocked host for {url}")
    if resp.status_code in (429, 500, 502, 503, 504):
        # Transient: sleep a touch and let tenacity-less callers see the status.
        time.sleep(2)
    return resp


def get_json(url: str, *, params: Optional[dict] = None, cache_key: Optional[str] = None,
             headers: Optional[dict] = None, force: bool = False) -> Optional[dict]:
    """GET JSON with on-disk caching. Returns None on non-200 or parse error."""
    key = cache_key or f"{url}?{json.dumps(params, sort_keys=True) if params else ''}"
    cpath = _cache_path(key, ".json")
    if cpath.exists() and not force:
        try:
            return json.loads(cpath.read_text())
        except Exception:
            pass
    resp = _request("GET", url, params=params, headers=headers)
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    cpath.write_text(json.dumps(data))
    return data


def get_bytes(url: str, *, headers: Optional[dict] = None, timeout: int = 60) -> Optional[bytes]:
    """GET raw bytes (PDFs). Returns None on failure."""
    resp = _request("GET", url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return None
    return resp.content


def get_text(url: str, *, headers: Optional[dict] = None, timeout: int = 60) -> Optional[tuple[str, str]]:
    """GET text content. Returns (text, content_type) or None."""
    resp = _request("GET", url, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        return None
    return resp.text, resp.headers.get("Content-Type", "")
