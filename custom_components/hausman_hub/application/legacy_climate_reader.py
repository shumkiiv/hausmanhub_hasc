"""One-shot read-only client for the retired external climate API.

Roadmap item 37. This is the only network surface of the migration wizard:
a single bounded GET of the legacy state endpoint with the existing
private-address validation. It has no command methods and never writes,
and the address and response live only in the options-flow memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..domain.climate_bridge import (
    ClimateBridgeTarget,
    UnsafeClimateBridgeTarget,
    climate_bridge_target,
)
from .climate_discovery import ClimateImportSnapshot
from .climate_import_legacy import import_climate_state

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class LegacyClimateReadError(RuntimeError):
    """The legacy climate state cannot be read or validated."""


class LegacyClimateStateReader:
    """Fetch one fresh legacy climate snapshot over a single GET."""

    def __init__(self, hass: HomeAssistant, target: ClimateBridgeTarget) -> None:
        self._hass = hass
        self._target = target

    async def async_fetch_state(self) -> ClimateImportSnapshot:
        """Return one validated snapshot, or fail closed with a bounded error."""

        try:
            from aiohttp import ClientError, ClientTimeout
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
        except Exception as error:  # pragma: no cover - aiohttp is always present in HA
            raise LegacyClimateReadError("http client is unavailable") from error
        timeout = ClientTimeout(total=10)
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                f"{self._target.origin}/endpoint/climate/api/v1/state",
                allow_redirects=False,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    raise LegacyClimateReadError(
                        f"legacy climate API answered HTTP {response.status}"
                    )
                payload: Any = await response.json(content_type=None)
        except ClientError as error:
            raise LegacyClimateReadError("legacy climate API is unreachable") from error
        except LegacyClimateReadError:
            raise
        except Exception as error:
            raise LegacyClimateReadError(
                "legacy climate state could not be decoded"
            ) from error
        try:
            snapshot = import_climate_state(payload)
        except Exception as error:
            raise LegacyClimateReadError(
                "legacy climate state does not match the fixed contract"
            ) from error
        if not snapshot.runtime_fresh:
            raise LegacyClimateReadError("legacy climate state is stale")
        return snapshot


def legacy_climate_target(value: object) -> ClimateBridgeTarget:
    """Validate one migration address with the existing private-address rules."""

    try:
        return climate_bridge_target(value)
    except UnsafeClimateBridgeTarget as error:
        raise LegacyClimateReadError(str(error)) from error
