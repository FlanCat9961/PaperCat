import logging

from papercat.core.logger import setup_logger


def test_setup_logger_creates_log_file_and_writes_message(tmp_path) -> None:
    logger = setup_logger("papercat-test", tmp_path, logging.INFO, "worker")

    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()

    log_file = tmp_path / "papercat-test.log"
    assert log_file.exists()
    assert "papercat-test[worker]: hello" in log_file.read_text(encoding="utf-8")


def test_setup_logger_replaces_existing_handlers(tmp_path) -> None:
    first = setup_logger("papercat-reuse", tmp_path, logging.INFO, "first")
    second = setup_logger("papercat-reuse", tmp_path, logging.DEBUG, "second")

    assert first is second
    assert len(second.handlers) == 2
    assert second.level == logging.DEBUG
