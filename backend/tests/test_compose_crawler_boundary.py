from backend.app.services.crawl_service import CrawlService


def test_crawler_is_internal_only_and_does_not_mount_backend_data() -> None:
    service = CrawlService(crawler_base_url="http://crawler:8100")

    assert service.crawler_base_url == "http://crawler:8100"
