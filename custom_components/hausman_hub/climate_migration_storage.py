"""Versioned Home Assistant storage adapter for the climate migration receipt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .application.climate_migration import (
    MIGRATION_CONTRACT_VERSION,
    ClimateMigrationReceipt,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store


class ClimateMigrationStorageError(RuntimeError):
    """Persisted migration receipt is damaged or unavailable."""


class HomeAssistantClimateMigrationStore:
    """Persist one bounded migration receipt per HausmanHub config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store

        self._store: Store[dict[str, object]] = Store(
            hass,
            MIGRATION_CONTRACT_VERSION,
            f"hausman_hub.climate_migration.{entry_id}",
        )

    async def async_load(self) -> ClimateMigrationReceipt | None:
        """Return no receipt before the first finished migration."""

        payload = await self._store.async_load()
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ClimateMigrationStorageError("stored migration receipt is invalid")
        contract = payload.get("contract")
        fingerprint = payload.get("fingerprint")
        device_ids = payload.get("created_device_ids")
        room_ids = payload.get("created_room_ids")
        mode = payload.get("mode")
        if (
            not isinstance(contract, dict)
            or contract.get("name") != "hausman-hub-climate-migration-receipt"
            or contract.get("version") != MIGRATION_CONTRACT_VERSION
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or not isinstance(device_ids, list)
            or not isinstance(room_ids, list)
            or any(not isinstance(value, str) for value in device_ids)
            or any(not isinstance(value, str) for value in room_ids)
            or mode not in {"automatic", "disabled"}
        ):
            raise ClimateMigrationStorageError("stored migration receipt is invalid")
        return ClimateMigrationReceipt(
            contract=dict(contract),
            fingerprint=fingerprint,
            created_device_ids=tuple(device_ids),
            created_room_ids=tuple(room_ids),
            mode=mode,
        )

    async def async_save(self, receipt: ClimateMigrationReceipt) -> None:
        """Persist the finished migration receipt for a later safe rollback."""

        await self._store.async_save(
            {
                "contract": receipt.contract,
                "fingerprint": receipt.fingerprint,
                "created_device_ids": list(receipt.created_device_ids),
                "created_room_ids": list(receipt.created_room_ids),
                "mode": receipt.mode,
            }
        )

    async def async_remove(self) -> None:
        """Delete the receipt after a successful rollback."""

        await self._store.async_remove()
