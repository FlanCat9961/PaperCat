from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from papercat.core.config import ProxyConfig
from papercat.core.exceptions import SourceNetworkError


class HttpClient:
    def __init__(
        self,
        *,
        proxy: ProxyConfig,
        timeout: float,
        user_agent: str,
        retry_attempts: int = 3,
    ) -> None:
        self.proxy = proxy
        self.timeout = timeout
        self.user_agent = user_agent
        self.retry_attempts = retry_attempts
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> HttpClient:
        proxy_url = self.proxy.url if self.proxy.enabled else None
        self._client = httpx.AsyncClient(
            proxy=proxy_url,
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        response = await self._request_with_retry("GET", url, params=params, headers=headers)
        return response.json()

    async def stream_to_file(
        self,
        url: str,
        dst: Path,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        try:
            response = await self._request_with_retry("GET", url, headers=headers)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(response.content)
        except Exception as exc:
            dst.unlink(missing_ok=True)
            if isinstance(exc, SourceNetworkError):
                raise
            raise SourceNetworkError(f"failed to stream {url} to {dst}: {exc}") from exc

    async def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._require_client()
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code == 429:
                    await asyncio.sleep(self._retry_after(response))
                    response = await client.request(method, url, **kwargs)
                if 500 <= response.status_code < 600:
                    raise SourceNetworkError(f"server error {response.status_code} for {url}")
                response.raise_for_status()
                return response
            except (
                httpx.NetworkError,
                httpx.RemoteProtocolError,
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                SourceNetworkError,
            ) as exc:
                last_error = exc
                if attempt == self.retry_attempts:
                    break
                await asyncio.sleep(min(30.0, 2.0 ** (attempt - 1)))
        raise SourceNetworkError(f"request failed for {url}: {last_error}")

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise SourceNetworkError("HttpClient must be used as an async context manager")
        return self._client

    @staticmethod
    def _retry_after(response: httpx.Response) -> float:
        value = response.headers.get("Retry-After")
        if value is None:
            return 1.0
        try:
            return max(0.0, float(value))
        except ValueError:
            return 1.0
