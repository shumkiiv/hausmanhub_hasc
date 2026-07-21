"""Versioned Home Assistant storage adapter for the private climate registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .application.climate_registry import (
    ClimateRegistryViolation,
    migrate_climate_registry_payload,
    registry_from_payload,
    registry_to_payload,
)
from .domain.climate import ClimateRegistry, REGISTRY_VERSION

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ClimateRegistryStorageError(RuntimeError):
    """Persisted climate registry data is damaged or unavailable."""


class _MigratingClimateRegistryStore(Store[dict[str, object]]):
    """Let Home Assistant rewrite the exact legacy registry payload once."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: object,
    ) -> dict[str, object]:
        del old_minor_version
        return migrate_climate_registry_payload(old_major_version, old_data)


class HomeAssistantClimateRegistryStore:
    """Persist one complete registry per single HausmanHub config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = _MigratingClimateRegistryStore(
            hass,
            REGISTRY_VERSION,
            f"hausman_hub.climate_registry.{entry_id}",
            max_readable_version=REGISTRY_VERSION,
        )

    async def async_load(self) -> ClimateRegistry:
        """Return an empty registry only when no registry has ever been saved."""

        # A migration failure raises from the store on purpose: the runtime
        # start catches it and fails the climate surface closed, matching the
        # contour migration path. Do not silence it into an empty registry.
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
