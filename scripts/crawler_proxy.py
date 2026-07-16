from __future__ import annotations

import os


def proxy_url() -> str | None:
    host = os.getenv("CRAWLER_PROXY_HOST", "").strip()
    port = os.getenv("CRAWLER_PROXY_PORT", "").strip()
    if not host or not port:
        return None
    return f"http://{host}:{port}"


def playwright_proxy() -> dict[str, str] | None:
    proxy = proxy_url()
    return {"server": proxy} if proxy else None


def configure_environment() -> None:
    proxy = proxy_url()
    if proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
    else:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(name, None)
