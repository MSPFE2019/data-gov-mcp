"""Model Context Protocol server for the api.data.gov ecosystem."""

from __future__ import annotations

import ipaddress
import hmac
import json
import os
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import uvicorn


mcp = FastMCP("data-gov")
DEFAULT_TIMEOUT_SECONDS = 30


def _api_key() -> str:
    return os.environ.get("DATA_GOV_API_KEY", "DEMO_KEY")


def _configured_hosts() -> set[str]:
    configured = os.environ.get("DATA_GOV_ALLOWED_HOSTS", "")
    return {host.strip().lower() for host in configured.split(",") if host.strip()}


def _is_public_address(hostname: str) -> bool:
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve API host '{hostname}'.") from exc

    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_unspecified
            or parsed.is_reserved
        ):
            return False
    return True


def _validate_endpoint(endpoint_url: str) -> None:
    parsed = urlparse(endpoint_url)
    hostname = (parsed.hostname or "").lower()
    configured_hosts = _configured_hosts()
    is_data_gov_host = hostname == "data.gov" or hostname.endswith(".data.gov")
    is_federal_host = hostname.endswith(".gov") or hostname.endswith(".mil")

    if parsed.scheme != "https" or not hostname:
        raise ValueError("endpoint_url must be an HTTPS URL with a hostname.")
    if configured_hosts and hostname not in configured_hosts:
        raise ValueError(
            f"Host '{hostname}' is not in DATA_GOV_ALLOWED_HOSTS."
        )
    if not configured_hosts and not (is_data_gov_host or is_federal_host):
        raise ValueError(
            "Only federal .gov/.mil hosts are allowed by default. "
            "Set DATA_GOV_ALLOWED_HOSTS for an explicit host allowlist."
        )
    if not _is_public_address(hostname):
        raise ValueError("Private, loopback, or otherwise non-public API hosts are not allowed.")


def _request_json(
    endpoint_url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    include_api_key: bool = True,
) -> Any:
    query = parse_qs(urlparse(endpoint_url).query, keep_blank_values=True)
    for key, value in (params or {}).items():
        if value is not None:
            query[key] = [str(value)]
    if include_api_key and "api_key" not in query:
        query["api_key"] = [_api_key()]

    parsed = urlparse(endpoint_url)
    request_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    headers = {"Accept": "application/json", "User-Agent": "data-gov-mcp/1.0"}
    if include_api_key:
        headers["X-Api-Key"] = _api_key()

    try:
        with urlopen(Request(request_url, headers=headers), timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"data.gov API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach data.gov API: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw.decode("utf-8", errors="replace")[:10000]}


@mcp.tool()
def call_federal_api(
    endpoint_url: str,
    parameters: dict[str, Any] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """Make a read-only GET request to an approved federal API endpoint."""
    _validate_endpoint(endpoint_url)
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be between 1 and 120.")
    return _request_json(
        endpoint_url,
        params=parameters,
        timeout=timeout_seconds,
        include_api_key=True,
    )


@mcp.tool()
def get_rate_limit_info(endpoint_url: str) -> dict[str, Any]:
    """Check an endpoint and return its response plus API rate-limit headers."""
    _validate_endpoint(endpoint_url)
    parsed = urlparse(endpoint_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if "api_key" not in query:
        query["api_key"] = [_api_key()]
    request_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "data-gov-mcp/1.0",
            "X-Api-Key": _api_key(),
        },
    )
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body = response.read()
            headers = {
                "limit": response.headers.get("X-RateLimit-Limit"),
                "remaining": response.headers.get("X-RateLimit-Remaining"),
            }
    except HTTPError as exc:
        raise RuntimeError(
            f"data.gov API returned HTTP {exc.code}: "
            f"{exc.read().decode('utf-8', errors='replace')[:2000]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach data.gov API: {exc.reason}") from exc

    try:
        payload: Any = json.loads(body)
    except json.JSONDecodeError:
        payload = {"text": body.decode("utf-8", errors="replace")[:10000]}
    return {"rate_limit": headers, "response": payload}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Protect the public MCP endpoint without exposing the data.gov key."""

    async def dispatch(self, request, call_next):
        expected = os.environ.get("MCP_SERVER_API_KEY", "")
        endpoint_path = os.environ.get("MCP_PATH", "/mcp")
        if request.url.path == endpoint_path:
            supplied = request.headers.get("X-MCP-API-Key", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return JSONResponse(
                    {"error": "A valid X-MCP-API-Key header is required."},
                    status_code=401,
                )
        return await call_next(request)


def _run_streamable_http() -> None:
    server_key = os.environ.get("MCP_SERVER_API_KEY", "")
    if not server_key:
        raise RuntimeError(
            "MCP_SERVER_API_KEY must be set when MCP_TRANSPORT=streamable-http."
        )

    mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8000"))
    mcp.settings.streamable_http_path = os.environ.get("MCP_PATH", "/mcp")
    configured_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "")
    if configured_hosts:
        mcp.settings.transport_security.allowed_hosts = [
            host.strip() for host in configured_hosts.split(",") if host.strip()
        ]
    app = mcp.streamable_http_app()
    app.add_middleware(ApiKeyMiddleware)
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "streamable-http":
        _run_streamable_http()
    elif transport == "stdio":
        mcp.run()
    else:
        raise ValueError("MCP_TRANSPORT must be 'stdio' or 'streamable-http'.")
