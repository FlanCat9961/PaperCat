from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response

from papercat.core.config import ProxyConfig
from papercat.core.exceptions import SourceNetworkError
from papercat.core.sources.http import HttpClient


@pytest.mark.asyncio
@respx.mock
async def test_get_json_returns_payload() -> None:
    respx.get("https://example.invalid/data").mock(return_value=Response(200, json={"ok": True}))

    async with HttpClient(proxy=ProxyConfig(), timeout=1, user_agent="PaperCat") as http:
        assert await http.get_json("https://example.invalid/data") == {"ok": True}


@pytest.mark.asyncio
@respx.mock
async def test_5xx_final_failure_raises() -> None:
    respx.get("https://example.invalid/fail").mock(return_value=Response(500))

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=1
    ) as http:
        with pytest.raises(SourceNetworkError):
            await http.get_json("https://example.invalid/fail")


@pytest.mark.asyncio
@respx.mock
async def test_stream_to_file_writes_bytes(tmp_path: Path) -> None:
    respx.get("https://example.invalid/image").mock(return_value=Response(200, content=b"abc"))
    dst = tmp_path / "image.part"

    async with HttpClient(proxy=ProxyConfig(), timeout=1, user_agent="PaperCat") as http:
        await http.stream_to_file("https://example.invalid/image", dst)

    assert dst.read_bytes() == b"abc"


@pytest.mark.asyncio
async def test_require_client_without_aenter_raises() -> None:
    http = HttpClient(proxy=ProxyConfig(), timeout=1, user_agent="PaperCat")
    with pytest.raises(SourceNetworkError):
        await http.get_json("https://example.invalid/x")


@pytest.mark.asyncio
@respx.mock
async def test_proxy_enabled_passes_proxy_url() -> None:
    respx.get("https://example.invalid/p").mock(return_value=Response(200, json={"ok": 1}))
    proxy = ProxyConfig(enabled=True, url="socks5://127.0.0.1:9050")
    async with HttpClient(proxy=proxy, timeout=1, user_agent="PaperCat") as http:
        assert await http.get_json("https://example.invalid/p") == {"ok": 1}


@pytest.mark.asyncio
@respx.mock
async def test_429_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("papercat.core.sources.http.asyncio.sleep", fake_sleep)
    route = respx.get("https://example.invalid/r").mock(
        side_effect=[
            Response(429, headers={"Retry-After": "0"}),
            Response(200, json={"ok": True}),
        ]
    )

    async with HttpClient(proxy=ProxyConfig(), timeout=1, user_agent="PaperCat") as http:
        assert await http.get_json("https://example.invalid/r") == {"ok": True}

    assert route.call_count == 2
    assert sleeps == [0.0]


@pytest.mark.asyncio
@respx.mock
async def test_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "papercat.core.sources.http.asyncio.sleep",
        lambda d: _noop(),
    )
    route = respx.get("https://example.invalid/x").mock(
        side_effect=[
            httpx.ConnectError("boom"),
            Response(200, json={"ok": 1}),
        ]
    )

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=3
    ) as http:
        assert await http.get_json("https://example.invalid/x") == {"ok": 1}
    assert route.call_count == 2


async def _noop() -> None:
    return None


@pytest.mark.asyncio
@respx.mock
async def test_connect_timeout_is_retried_then_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "papercat.core.sources.http.asyncio.sleep",
        lambda d: _noop(),
    )
    route = respx.get("https://example.invalid/slow").mock(
        side_effect=httpx.ConnectTimeout("too slow")
    )

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=2
    ) as http:
        with pytest.raises(SourceNetworkError):
            await http.get_json("https://example.invalid/slow")

    assert route.call_count == 2  # retried, not bubbled raw


@pytest.mark.asyncio
@respx.mock
async def test_network_error_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "papercat.core.sources.http.asyncio.sleep",
        lambda d: _noop(),
    )
    respx.get("https://example.invalid/dead").mock(side_effect=httpx.ConnectError("nope"))

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=2
    ) as http:
        with pytest.raises(SourceNetworkError):
            await http.get_json("https://example.invalid/dead")


@pytest.mark.asyncio
@respx.mock
async def test_4xx_raises_via_raise_for_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "papercat.core.sources.http.asyncio.sleep",
        lambda d: _noop(),
    )
    respx.get("https://example.invalid/bad").mock(return_value=Response(404))

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=1
    ) as http:
        with pytest.raises(SourceNetworkError):
            await http.get_json("https://example.invalid/bad")


def test_retry_after_parsing() -> None:
    assert HttpClient._retry_after(httpx.Response(429)) == 1.0
    assert HttpClient._retry_after(httpx.Response(429, headers={"Retry-After": "2.5"})) == 2.5
    assert HttpClient._retry_after(httpx.Response(429, headers={"Retry-After": "junk"})) == 1.0
    assert HttpClient._retry_after(httpx.Response(429, headers={"Retry-After": "-3"})) == 0.0


@pytest.mark.asyncio
@respx.mock
async def test_stream_to_file_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "papercat.core.sources.http.asyncio.sleep",
        lambda d: _noop(),
    )
    respx.get("https://example.invalid/img").mock(side_effect=httpx.ConnectError("nope"))
    dst = tmp_path / "out" / "x.png"

    async with HttpClient(
        proxy=ProxyConfig(), timeout=1, user_agent="PaperCat", retry_attempts=1
    ) as http:
        with pytest.raises(SourceNetworkError):
            await http.stream_to_file("https://example.invalid/img", dst)

    assert not dst.exists()


@pytest.mark.asyncio
async def test_stream_to_file_wraps_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = tmp_path / "y.png"

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk on fire")

    async with HttpClient(proxy=ProxyConfig(), timeout=1, user_agent="PaperCat") as http:
        monkeypatch.setattr(http, "_request_with_retry", boom)
        with pytest.raises(SourceNetworkError) as info:
            await http.stream_to_file("https://example.invalid/y", dst)
    assert "disk on fire" in str(info.value)
