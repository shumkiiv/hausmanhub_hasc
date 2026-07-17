"""Public Android and private administrator climate projections.

The normal tablet contract deliberately contains only stable HASC identifiers.
Private Climate API device identifiers and Home Assistant entity bindings are
available only through the separate administrator projection.
"""

from __future__ import annotations

from ..domain.climate import ClimateRegistry
from .climate_import import ClimateImportSnapshot
from .climate_registry import reconcile_climate_registry


ANDROID_CLIMATE_CONTRACT_NAME = "hausman-hasc-home"
ANDROID_CLIMATE_CONTRACT_VERSION = 1


def android_climate_snapshot(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
    *,
    commands_enabled: bool,
) -> dict[str, object]:
    """Build the fixed tablet contract without any private source binding."""

    reconciliation = reconcile_climate_registry(registry, snapshot)
    imported_by_source = {device.source_id: device for device in snapshot.devices}
    devices_by_room: dict[str, list[dict[str, object]]] = {
        room.room_id: [] for room in registry.rooms
    }
    for device in registry.devices:
        imported = imported_by_source.get(device.source_id)
        exact_match = imported is not None and imported.room_id == device.room_id
        devices_by_room[device.room_id].append(
            {
                "id": device.device_id,
                "name": device.name,
                "kind": device.kind.value,
                "control_scope": device.control_scope.value,
                "capabilities": [value.value for value in device.capabilities],
                "available": bool(exact_match and imported.available),
                "state": imported.state if exact_match else "unknown",
            }
        )

    rooms: list[dict[str, object]] = []
    for room in registry.rooms:
        imported = snapshot.room(room.room_id)
        rooms.append(
            {
                "id": room.room_id,
                "name": room.name,
                "temperature": imported.temperature if imported else None,
                "humidity": imported.humidity if imported else None,
                "target_temperature": (
                    imported.target_temperature if imported else None
                ),
                "target_humidity": imported.target_humidity if imported else None,
                "mode": imported.mode if imported else None,
                "authority_eligible": bool(
                    imported is not None and imported.authority_eligible
                ),
                "devices": devices_by_room[room.room_id],
            }
        )

    return {
        "contract": {
            "name": ANDROID_CLIMATE_CONTRACT_NAME,
            "version": ANDROID_CLIMATE_CONTRACT_VERSION,
        },
        "generated_at": snapshot.generated_at,
        "climate": {
            "fresh": snapshot.runtime_fresh,
            "commands_enabled": commands_enabled,
        },
        "rooms": rooms,
        "reconciliation": {
            "matches": reconciliation.matches,
            "matched_device_ids": list(reconciliation.matched_device_ids),
            "missing_device_ids": list(reconciliation.missing_device_ids),
            "room_mismatch_device_ids": list(
                reconciliation.room_mismatch_device_ids
            ),
            "unregistered_device_count": len(
                reconciliation.unregistered_source_ids
            ),
        },
    }


def admin_climate_import_snapshot(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> dict[str, object]:
    """Build the local-administrator discovery and reconciliation payload."""

    reconciliation = reconcile_climate_registry(registry, snapshot)
    return {
        "generated_at": snapshot.generated_at,
        "fresh": snapshot.runtime_fresh,
        "rooms": [
            {
                "id": room.room_id,
                "name": room.name,
                "authority_eligible": room.authority_eligible,
            }
            for room in snapshot.rooms
        ],
        "candidates": [
            {
                "source_id": device.source_id,
                "name": device.name,
                "room_id": device.room_id,
                "available": device.available,
                "command_types": list(device.command_types),
                "suggested_kinds": [value.value for value in device.suggested_kinds],
            }
            for device in snapshot.devices
        ],
        "reconciliation": {
            "matches": reconciliation.matches,
            "matched_device_ids": list(reconciliation.matched_device_ids),
            "missing_device_ids": list(reconciliation.missing_device_ids),
            "room_mismatch_device_ids": list(
                reconciliation.room_mismatch_device_ids
            ),
            "unregistered_source_ids": list(
                reconciliation.unregistered_source_ids
            ),
        },
    }
