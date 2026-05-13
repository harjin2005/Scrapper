import structlog
from scraper.logger import get_logger


def test_get_logger_returns_bound_logger():
    log = get_logger("test_component")
    assert log is not None


def test_logger_has_component_context():
    import structlog.testing
    with structlog.testing.capture_logs() as cap_logs:
        log = get_logger("pdf_extractor")
        log.info("extraction_started", instrument_no="2026012345")
    assert len(cap_logs) == 1
    assert cap_logs[0]["component"] == "pdf_extractor"
    assert cap_logs[0]["instrument_no"] == "2026012345"
    assert cap_logs[0]["event"] == "extraction_started"
