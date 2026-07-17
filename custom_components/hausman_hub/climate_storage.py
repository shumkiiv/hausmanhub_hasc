"""Versioned Home Assistant storage adapter for the private climate registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .application.climate_registry import (
    ClimateRegistryViolation,
    registry_from_payload,
    registry_to_payload,
)
from .domain.climate import ClimateRegistry, REGISTRY_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ClimateRegistryStorageError(RuntimeError):
    """Persisted climate registry data is damaged or unavailable."""


class HomeAssistantClimateRegistryStore:
    """Persist one complete registry per single HASC config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = Store(
            hass,
            REGISTRY_VERSION,
            f"hausman_hub.climate_registry.{entry_id}",
        )

    async def async_load(self) -> ClimateRegistry:
        """Return an empty registry only when no registry has ever been saved."""

        payload = await self._store.async_load()
        if payload is None:
            return ClimateRegistry()
        try:
            return registry_from_payload(payload)
        except ClimateRegistryViolation as error:
            raise ClimateRegistryStorageError("stored climate registry is invalid") from error

    async def async_save(self, registry: ClimateRegistry) -> None:
        """Save only the exact validated registry payload."""

        await self._store.async_save(registry_to_payload(registry))
