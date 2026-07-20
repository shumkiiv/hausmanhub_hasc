"""Versioned Home Assistant storage adapter for HausmanHub contour definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .application.contours import (
    ContourRegistryViolation,
    contour_registry_from_payload,
    contour_registry_to_payload,
    migrate_contour_registry_payload,
)
from .domain.contours import CONTOUR_REGISTRY_VERSION, ContourRegistry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ContourStorageError(RuntimeError):
    """Persisted contour data is damaged or unavailable."""


class _MigratingContourStore(Store[dict[str, object]]):
    """Let Home Assistant rewrite the exact legacy contour payload once."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: object,
    ) -> dict[str, object]:
        del old_minor_version
        return migrate_contour_registry_payload(old_major_version, old_data)


class HomeAssistantContourStore:
    """Persist one complete contour registry per HausmanHub config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = _MigratingContourStore(
            hass,
            CONTOUR_REGISTRY_VERSION,
            f"hausman_hub.contours.{entry_id}",
            max_readable_version=CONTOUR_REGISTRY_VERSION,
        )

    async def async_load(self) -> ContourRegistry:
        """Return an empty registry only before the first contour is saved."""

        payload = await self._store.async_load()
        if payload is None:
            return ContourRegistry()
        try:
            return contour_registry_from_payload(payload)
        except ContourRegistryViolation as error:
            raise ContourStorageError("stored contour registry is invalid") from error

    async def async_save(self, registry: ContourRegistry) -> None:
        """Save only the exact validated contour payload."""

        await self._store.async_save(contour_registry_to_payload(registry))
