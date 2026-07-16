from scripts import crawler_proxy


def test_proxy_is_disabled_when_host_or_port_is_empty(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_PROXY_HOST", "host.docker.internal")
    monkeypatch.setenv("CRAWLER_PROXY_PORT", "")

    assert crawler_proxy.proxy_url() is None
    assert crawler_proxy.playwright_proxy() is None


def test_proxy_builds_http_server_for_all_clients(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_PROXY_HOST", "host.docker.internal")
    monkeypatch.setenv("CRAWLER_PROXY_PORT", "7897")

    assert crawler_proxy.proxy_url() == "http://host.docker.internal:7897"
    assert crawler_proxy.playwright_proxy() == {
        "server": "http://host.docker.internal:7897"
    }

    crawler_proxy.configure_environment()

    assert crawler_proxy.os.environ["HTTP_PROXY"] == "http://host.docker.internal:7897"
    assert crawler_proxy.os.environ["HTTPS_PROXY"] == "http://host.docker.internal:7897"


def test_proxy_environment_is_cleared_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CRAWLER_PROXY_HOST", "")
    monkeypatch.setenv("CRAWLER_PROXY_PORT", "")
    monkeypatch.setenv("HTTP_PROXY", "http://old-proxy:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://old-proxy:1")

    crawler_proxy.configure_environment()

    assert "HTTP_PROXY" not in crawler_proxy.os.environ
    assert "HTTPS_PROXY" not in crawler_proxy.os.environ
