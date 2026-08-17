"""Model Context Protocol server for the api.data.gov ecosystem."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


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


if __name__ == "__main__":
    mcp.run()
