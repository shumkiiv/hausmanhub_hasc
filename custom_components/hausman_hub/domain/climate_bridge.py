"""Validated local-only target for the typed Climate API adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from urllib.parse import urlsplit


_PRIVATE_V4 = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
)
_PRIVATE_V6 = IPv6Network("fc00::/7")


class UnsafeClimateBridgeTarget(ValueError):
    """The configured target is not one exact private HTTP origin."""


class ClimateBridgeMode(StrEnum):
    """The only rollout modes supported by the typed climate bridge."""

    DISABLED = "disabled"
    SHADOW = "shadow"
    CANARY = "canary"


@dataclass(frozen=True, slots=True)
class ClimateBridgeTarget:
    """One normalized private origin; fixed API paths are appended elsewhere."""

    origin: str


def climate_bridge_target(value: object) -> ClimateBridgeTarget:
    """Accept only HTTP(S) with a literal loopback or private-network address."""

    if not isinstance(value, str) or not value or len(value) > 255:
        raise UnsafeClimateBridgeTarget("climate bridge target is required")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeClimateBridgeTarget("climate bridge target must use HTTP or HTTPS")
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise UnsafeClimateBridgeTarget("climate bridge target must be one exact origin")
    try:
        address = ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as error:
        raise UnsafeClimateBridgeTarget(
            "climate bridge target must use a literal private address"
        ) from error
    if not _is_private_home_address(address):
        raise UnsafeClimateBridgeTarget(
            "climate bridge target must use a literal private address"
        )
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    host = f"[{address.compressed}]" if isinstance(address, IPv6Address) else str(address)
    return ClimateBridgeTarget(origin=f"{parsed.scheme}://{host}:{port}")


def _is_private_home_address(address: IPv4Address | IPv6Address) -> bool:
    if address.is_loopback:
        return True
    if isinstance(address, IPv4Address):
        return any(address in network for network in _PRIVATE_V4)
    mapped = address.ipv4_mapped
    if mapped is not None:
        return mapped.is_loopback or any(mapped in network for network in _PRIVATE_V4)
    return address in _PRIVATE_V6
