import subprocess
from dataclasses import dataclass

from papercat.core.notifier import Notifier, NotifyEvent, NotifyEventType


@dataclass
class FakeNotificationConfig:
    enabled: bool = True
    on_crawl_done: bool = True
    on_cleanup_done: bool = True
    on_error: bool = True


def test_disabled_notifier_does_not_call_runner() -> None:
    calls = []
    notifier = Notifier(
        FakeNotificationConfig(enabled=False), lambda *args, **kwargs: calls.append(args)
    )

    notifier.notify(NotifyEvent(NotifyEventType.ERROR, "title", "body", "critical"))

    assert calls == []


def test_disabled_event_does_not_call_runner() -> None:
    calls = []
    notifier = Notifier(
        FakeNotificationConfig(on_error=False), lambda *args, **kwargs: calls.append(args)
    )

    notifier.notify(NotifyEvent(NotifyEventType.ERROR, "title", "body", "critical"))

    assert calls == []


def test_notify_send_arguments() -> None:
    calls = []

    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0)

    Notifier(FakeNotificationConfig(), runner).notify(
        NotifyEvent(NotifyEventType.CRAWL_DONE, "done", "body", "low")
    )

    assert calls[0][0][0] == [
        "notify-send",
        "--app-name=PaperCat",
        "--urgency=low",
        "done",
        "body",
    ]


def test_runner_exception_does_not_escape() -> None:
    def runner(*args, **kwargs):
        raise FileNotFoundError("notify-send")

    Notifier(FakeNotificationConfig(), runner).notify(NotifyEvent(NotifyEventType.ERROR, "x", "y"))
