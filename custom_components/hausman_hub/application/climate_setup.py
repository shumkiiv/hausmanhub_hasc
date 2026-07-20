"""Stable, source-independent contracts for configuring climate in HASC."""

from __future__ import annotations

from ..domain.climate import ClimateRegistry
from .climate_import import ClimateImportSnapshot


CLIMATE_ROOMS_CONTRACT_NAME = "hausman-hasc-climate-rooms"
CLIMATE_ROOMS_CONTRACT_VERSION = 1
MAX_AVAILABLE_CLIMATE_ROOMS = 256

_ROOM_STATUS_NAMES = {
    "available": "Можно выбрать",
    "data_stale": "Нужно обновить данные",
    "source_missing": "Комната больше не найдена",
}


def climate_available_rooms(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> dict[str, object]:
    """Return every discovered or configured room using only stable HASC IDs."""

    if not isinstance(registry, ClimateRegistry):
        raise ValueError("climate room registry must be valid")
    if not isinstance(snapshot, ClimateImportSnapshot):
        raise ValueError("climate room snapshot must be valid")

    configured = {room.room_id: room for room in registry.rooms}
    imported = {room.room_id: room for room in snapshot.rooms}
    room_ids = configured.keys() | imported.keys()
    if len(room_ids) > MAX_AVAILABLE_CLIMATE_ROOMS:
        raise ValueError("too many available climate rooms")
    rooms: list[dict[str, object]] = []
    for room_id in sorted(room_ids):
        configured_room = configured.get(room_id)
        imported_room = imported.get(room_id)
        if not snapshot.runtime_fresh:
            status = "data_stale"
        elif imported_room is None:
            status = "source_missing"
        else:
            status = "available"
        if configured_room is not None:
            room_name = configured_room.name
        elif imported_room is not None:
            room_name = imported_room.name
        else:  # pragma: no cover - the room id came from one of these mappings
            raise ValueError("available climate room has no source")
        rooms.append(
            {
                "id": room_id,
                "name": room_name,
                "configured": configured_room is not None,
                "selectable": status == "available",
                "status": status,
            }
        )

    return {
        "contract": {
            "name": CLIMATE_ROOMS_CONTRACT_NAME,
            "version": CLIMATE_ROOMS_CONTRACT_VERSION,
        },
        "generated_at": snapshot.generated_at,
        "data_status": "current" if snapshot.runtime_fresh else "stale",
        "selection_allowed": any(room["selectable"] is True for room in rooms),
        "display_names": {"room_status": dict(_ROOM_STATUS_NAMES)},
        "rooms": rooms,
    }
