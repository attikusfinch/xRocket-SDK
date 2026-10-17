"""Small shared transport with explicit ownership and safe error messages."""

from ipaddress import ip_address
from math import isfinite
from typing import Any, Literal, TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, TypeAdapter, ValidationError

from .errors import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RequestTimeoutError,
    ResponseValidationError,
    ServerError,
    TransportError,
)

T = TypeVar("T")
Environment = Literal["mainnet", "testnet"]
Query = list[tuple[str, str | int]]


def _base_url(value: str) -> str:
    try:
        url = httpx.URL(value)
        loopback = url.host == "localhost"
        try:
            loopback = loopback or ip_address(url.host).is_loopback
        except ValueError:
            pass
        if (
            not url.host
            or value != value.strip()
            or "@" in urlsplit(value).netloc
            or url.username
            or url.password
            or "?" in value
            or "#" in value
            or url.path not in ("", "/")
            or (url.scheme != "https" and not (url.scheme == "http" and loopback))
        ):
            raise ValueError
        return str(url).rstrip("/")
    except (ValueError, httpx.InvalidURL):
        raise ValueError(
            "base_url must be an HTTPS origin (HTTP is allowed for loopback)"
        ) from None


def _decode(response: httpx.Response, adapter: TypeAdapter[T]) -> T:
    if not 200 <= response.status_code < 300:
        problem: dict[str, Any] = {}
        try:
            body = response.json()
            if isinstance(body, dict):
                problem = body
        except ValueError:
            pass
        errors: dict[int, type[APIError]] = {
            401: AuthenticationError,
            403: PermissionDeniedError,
            404: NotFoundError,
            429: RateLimitError,
        }
        error = (
            ServerError
            if response.status_code >= 500
            else errors.get(response.status_code, APIError)
        )
        raise error(
            status_code=response.status_code,
            problem=problem,
            request_id=response.headers.get("x-request-id"),
            retry_after=response.headers.get("retry-after"),
        )
    try:
        return adapter.validate_json(response.content)
    except (ValidationError, ValueError):
        raise ResponseValidationError("API response did not match the expected schema") from None


class _TransportConfig:
    def __init__(self, *, api_token: str | None, base_url: str, timeout: float) -> None:
        self._base_url = _base_url(base_url)
        if not isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self._timeout = timeout
        if api_token is not None and (
            not api_token.strip() or "\r" in api_token or "\n" in api_token
        ):
            raise ValueError("api_token must be a nonempty single-line string")
        self._api_token = SecretStr(api_token) if api_token is not None else None
        self._closed = False

    def _request_options(self, path: str, authenticated: bool) -> tuple[str, dict[str, str]]:
        if self._closed:
            raise RuntimeError("Client is closed")
        if not path.startswith("/api/") or "?" in path or "#" in path:
            raise ValueError("SDK request path must be relative and contain no query or fragment")
        if authenticated and self._api_token is None:
            raise AuthenticationError()
        headers = {"Accept": "application/json"}
        if self._api_token is not None:
            headers["Authorization"] = f"Bearer {self._api_token.get_secret_value()}"
        return self._base_url + path, headers


class SyncTransport(_TransportConfig):
    def __init__(
        self,
        *,
        api_token: str | None,
        base_url: str,
        timeout: float,
        http_client: httpx.Client | None,
    ) -> None:
        super().__init__(api_token=api_token, base_url=base_url, timeout=timeout)
        self._owns_client = http_client is None
        self._client = http_client if http_client is not None else httpx.Client()

    def get(
        self,
        path: str,
        adapter: TypeAdapter[T],
        *,
        params: Query | None = None,
        authenticated: bool = True,
    ) -> T:
        url, headers = self._request_options(path, authenticated)
        try:
            request = self._client.build_request(
                "GET",
                url,
                params=tuple(params) if params is not None else None,
                headers=headers,
                timeout=self._timeout,
            )
            if self._api_token is None:
                request.headers.pop("Authorization", None)
            response = self._client.send(request, follow_redirects=False, auth=None)
        except httpx.TimeoutException:
            raise RequestTimeoutError("HTTP request timed out") from None
        except httpx.RequestError:
            raise TransportError("HTTP request failed") from None
        return _decode(response, adapter)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                self._client.close()


class AsyncTransport(_TransportConfig):
    def __init__(
        self,
        *,
        api_token: str | None,
        base_url: str,
        timeout: float,
        http_client: httpx.AsyncClient | None,
    ) -> None:
        super().__init__(api_token=api_token, base_url=base_url, timeout=timeout)
        self._owns_client = http_client is None
        self._client = http_client if http_client is not None else httpx.AsyncClient()

    async def get(
        self,
        path: str,
        adapter: TypeAdapter[T],
        *,
        params: Query | None = None,
        authenticated: bool = True,
    ) -> T:
        url, headers = self._request_options(path, authenticated)
        try:
            request = self._client.build_request(
                "GET",
                url,
                params=tuple(params) if params is not None else None,
                headers=headers,
                timeout=self._timeout,
            )
            if self._api_token is None:
                request.headers.pop("Authorization", None)
            response = await self._client.send(request, follow_redirects=False, auth=None)
        except httpx.TimeoutException:
            raise RequestTimeoutError("HTTP request timed out") from None
        except httpx.RequestError:
            raise TransportError("HTTP request failed") from None
        return _decode(response, adapter)

    async def aclose(self) -> None:
        if not self._closed:
            self._closed = True
            if self._owns_client:
                await self._client.aclose()
