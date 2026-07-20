"""Stable, source-independent contracts for configuring climate in HASC."""

from __future__ import annotations

import hashlib
import json

from ..domain.climate import ClimateRegistry
from .contours import ContourRegistryViolation, climate_room_parameters
from .climate_import import ClimateImportSnapshot
from .public_climate_values import public_climate_display_names


CLIMATE_ROOMS_CONTRACT_NAME = "hausman-hasc-climate-rooms"
CLIMATE_ROOMS_CONTRACT_VERSION = 1
MAX_AVAILABLE_CLIMATE_ROOMS = 256
CLIMATE_DEVICE_CANDIDATES_CONTRACT_NAME = "hausman-hasc-climate-device-candidates"
CLIMATE_DEVICE_CANDIDATES_CONTRACT_VERSION = 1
MAX_CLIMATE_DEVICE_CANDIDATES = 1024
JSON_SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
CLIMATE_ROOM_SUGGESTIONS_CONTRACT_NAME = "hausman-hasc-climate-room-suggestions"
CLIMATE_ROOM_SUGGESTIONS_CONTRACT_VERSION = 1
CLIMATE_DRAFT_CONTRACT_NAME = "hausman-hasc-climate-draft"
CLIMATE_DRAFT_CONTRACT_VERSION = 1
CLIMATE_SETUP_OPTIONS_CONTRACT_NAME = "hausman-hasc-climate-setup-options"
CLIMATE_SETUP_OPTIONS_CONTRACT_VERSION = 1
MAX_CLIMATE_DRAFT_NAME_LENGTH = 120
MAX_CLIMATE_DRAFT_ROOMS = 128
MAX_CLIMATE_DRAFT_DEVICES = 512

_CLIMATE_DRAFT_MODES = frozenset({"observe", "automatic"})
_CLIMATE_DRAFT_FIELDS = frozenset(
    {"snapshot_revision", "name", "mode", "rooms"}
)
_CLIMATE_DRAFT_ROOM_FIELDS = frozenset(
    {
        "room_id",
        "target_temperature",
        "target_humidity",
        "strategy",
        "devices",
    }
)
_CLIMATE_DRAFT_DEVICE_FIELDS = frozenset({"candidate_id", "type"})
_DRAFT_MODE_NAMES = {
    "observe": "Только наблюдение",
    "automatic": "Автоматическое управление",
}
_DRAFT_STRATEGY_NAMES = {
    "soft": "Плавно",
    "normal": "Обычно",
    "aggressive": "Быстро",
}

_ROOM_STATUS_NAMES = {
    "available": "Можно выбрать",
    "data_stale": "Нужно обновить данные",
    "source_missing": "Комната больше не найдена",
}
_CANDIDATE_STATUS_NAMES = {
    "available": "Можно добавить",
    "already_configured": "Уже добавлено",
    "unavailable": "Устройство недоступно",
    "unsupported": "Тип устройства не поддерживается",
    "data_stale": "Нужно обновить данные",
    "source_missing": "Устройство больше не найдено",
    "registry_mismatch": "Нужно проверить привязку устройства",
}
_SUGGESTION_CONFIDENCE_NAMES = {
    "high": "Комната определена",
    "none": "Нет безопасного предложения",
}
_SUGGESTION_REASON_NAMES = {
    "detected_room": "Устройство найдено в этой комнате",
    "already_configured": "Устройство уже назначено этой комнате",
    "device_unavailable": "Устройство сейчас недоступно",
    "unsupported_device": "Тип устройства не поддерживается",
    "data_stale": "Нужно обновить данные",
    "device_missing": "Настроенное устройство больше не найдено",
    "registry_mismatch": "Текущая привязка не совпадает с настройкой HASC",
    "room_unavailable": "Комната сейчас недоступна для выбора",
}


class ClimateSetupViolation(ValueError):
    """A climate setup request is unsafe, stale, or internally inconsistent."""

    def __init__(self, message: str, *, code: str = "invalid_draft") -> None:
        super().__init__(message)
        self.code = code


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


def climate_device_candidates(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> dict[str, object]:
    """Return bounded device choices without exposing their private bindings."""

    if not isinstance(registry, ClimateRegistry):
        raise ValueError("climate device registry must be valid")
    if not isinstance(snapshot, ClimateImportSnapshot):
        raise ValueError("climate device snapshot must be valid")

    configured = {device.source_id: device for device in registry.devices}
    imported = {device.source_id: device for device in snapshot.devices}
    source_ids = _ordered_candidate_source_ids(registry, snapshot)

    candidates: list[dict[str, object]] = []
    private_revision_values: list[dict[str, object]] = []
    for index, source_id in enumerate(source_ids, start=1):
        configured_device = configured.get(source_id)
        imported_device = imported.get(source_id)
        if configured_device is not None:
            name = configured_device.name
            room_id = (
                imported_device.room_id
                if imported_device is not None
                else configured_device.room_id
            )
        elif imported_device is not None:
            name = imported_device.name
            room_id = imported_device.room_id
        else:  # pragma: no cover - the source id came from one of these mappings
            raise ValueError("climate device candidate has no source")

        suggested_types = (
            []
            if imported_device is None
            else [kind.value for kind in imported_device.suggested_kinds]
        )
        configured_type = (
            None if configured_device is None else configured_device.kind.value
        )
        available = bool(
            snapshot.runtime_fresh
            and imported_device is not None
            and imported_device.available
        )
        if not snapshot.runtime_fresh:
            status = "data_stale"
        elif imported_device is None:
            status = "source_missing"
        elif configured_device is not None and (
            configured_device.room_id != imported_device.room_id
            or configured_device.kind not in imported_device.suggested_kinds
        ):
            status = "registry_mismatch"
        elif not suggested_types:
            status = "unsupported"
        elif not imported_device.available:
            status = "unavailable"
        elif configured_device is not None:
            status = "already_configured"
        else:
            status = "available"

        candidates.append(
            {
                "candidate_id": f"candidate_{index:04d}",
                "name": name,
                "room_id": room_id,
                "available": available,
                "configured": configured_device is not None,
                "configured_device_id": (
                    None
                    if configured_device is None
                    else configured_device.device_id
                ),
                "configured_room_id": (
                    None if configured_device is None else configured_device.room_id
                ),
                "configured_type": configured_type,
                "suggested_types": suggested_types,
                "recommended_type": (
                    suggested_types[0] if suggested_types else None
                ),
                "selectable": status == "available",
                "status": status,
            }
        )
        private_revision_values.append(
            {
                "source_id": source_id,
                "configured_device_id": (
                    None
                    if configured_device is None
                    else configured_device.device_id
                ),
                "configured_room_id": (
                    None if configured_device is None else configured_device.room_id
                ),
                "configured_type": configured_type,
                "imported": (
                    None
                    if imported_device is None
                    else {
                        "name": imported_device.name,
                        "room_id": imported_device.room_id,
                        "available": imported_device.available,
                        "command_types": list(imported_device.command_types),
                        "suggested_types": suggested_types,
                    }
                ),
            }
        )

    device_kind_names = public_climate_display_names()["device_kinds"]
    return {
        "contract": {
            "name": CLIMATE_DEVICE_CANDIDATES_CONTRACT_NAME,
            "version": CLIMATE_DEVICE_CANDIDATES_CONTRACT_VERSION,
        },
        "generated_at": snapshot.generated_at,
        "snapshot_revision": _json_safe_revision(
            {
                "fresh": snapshot.runtime_fresh,
                "candidates": private_revision_values,
            }
        ),
        "data_status": "current" if snapshot.runtime_fresh else "stale",
        "selection_allowed": any(
            candidate["selectable"] is True for candidate in candidates
        ),
        "display_names": {
            "device_types": dict(device_kind_names),
            "candidate_status": dict(_CANDIDATE_STATUS_NAMES),
        },
        "candidates": candidates,
    }


def climate_room_suggestions(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> dict[str, object]:
    """Suggest only explicit source-room matches and never assign automatically."""

    rooms_payload = climate_available_rooms(registry, snapshot)
    candidates_payload = climate_device_candidates(registry, snapshot)
    room_by_id = {room["id"]: room for room in rooms_payload["rooms"]}  # type: ignore[index]
    suggestions: list[dict[str, object]] = []
    for candidate in candidates_payload["candidates"]:  # type: ignore[index]
        candidate_status = candidate["status"]
        suggested_room_id: object = None
        suggested_room_name: object = None
        confidence = "none"
        if candidate_status == "already_configured":
            proposal_room_id = candidate["configured_room_id"]
        elif candidate_status in {"available", "unavailable", "unsupported"}:
            proposal_room_id = candidate["room_id"]
        else:
            proposal_room_id = None

        proposal_room = (
            room_by_id.get(proposal_room_id)
            if isinstance(proposal_room_id, str)
            else None
        )
        if proposal_room is not None and proposal_room["status"] == "available":
            suggested_room_id = proposal_room["id"]
            suggested_room_name = proposal_room["name"]
            confidence = "high"

        can_accept = bool(
            candidate_status == "available"
            and proposal_room is not None
            and proposal_room["selectable"] is True
        )
        if candidate_status == "available":
            reason = "detected_room" if can_accept else "room_unavailable"
        elif candidate_status == "already_configured":
            reason = "already_configured"
        elif candidate_status == "unavailable":
            reason = "device_unavailable"
        elif candidate_status == "unsupported":
            reason = "unsupported_device"
        elif candidate_status == "data_stale":
            reason = "data_stale"
        elif candidate_status == "source_missing":
            reason = "device_missing"
        elif candidate_status == "registry_mismatch":
            reason = "registry_mismatch"
        else:  # pragma: no cover - candidate statuses are closed above
            raise ValueError("climate candidate status is unsupported")

        suggestions.append(
            {
                "candidate_id": candidate["candidate_id"],
                "device_name": candidate["name"],
                "candidate_status": candidate_status,
                "suggested_room_id": suggested_room_id,
                "suggested_room_name": suggested_room_name,
                "confidence": confidence,
                "reason": reason,
                "can_accept": can_accept,
            }
        )

    return {
        "contract": {
            "name": CLIMATE_ROOM_SUGGESTIONS_CONTRACT_NAME,
            "version": CLIMATE_ROOM_SUGGESTIONS_CONTRACT_VERSION,
        },
        "generated_at": candidates_payload["generated_at"],
        "snapshot_revision": candidates_payload["snapshot_revision"],
        "data_status": candidates_payload["data_status"],
        "assignment_allowed": any(
            suggestion["can_accept"] is True for suggestion in suggestions
        ),
        "confirmation_required": True,
        "display_names": {
            "confidence": dict(_SUGGESTION_CONFIDENCE_NAMES),
            "reason": dict(_SUGGESTION_REASON_NAMES),
        },
        "suggestions": suggestions,
    }


def create_climate_contour_draft(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
    payload: object,
) -> dict[str, object]:
    """Create one deterministic, non-persistent contour draft from fresh choices."""

    if not isinstance(registry, ClimateRegistry):
        raise ClimateSetupViolation("climate draft registry must be valid")
    if not isinstance(snapshot, ClimateImportSnapshot):
        raise ClimateSetupViolation("climate draft snapshot must be valid")
    values = _exact_mapping(payload, _CLIMATE_DRAFT_FIELDS, "climate draft")
    requested_revision = values["snapshot_revision"]
    if (
        type(requested_revision) is not int
        or not 0 <= requested_revision <= JSON_SAFE_INTEGER_MAXIMUM
    ):
        raise ClimateSetupViolation("climate draft snapshot revision is invalid")

    candidates_payload = climate_device_candidates(registry, snapshot)
    current_revision = candidates_payload["snapshot_revision"]
    if not snapshot.runtime_fresh:
        raise ClimateSetupViolation(
            "climate draft needs current discovery data",
            code="data_stale",
        )
    if requested_revision != current_revision:
        raise ClimateSetupViolation(
            "climate device choices changed",
            code="snapshot_changed",
        )

    name = values["name"]
    if (
        not isinstance(name, str)
        or not name
        or name != name.strip()
        or len(name) > MAX_CLIMATE_DRAFT_NAME_LENGTH
    ):
        raise ClimateSetupViolation("climate draft name is invalid")
    mode = values["mode"]
    if not isinstance(mode, str) or mode not in _CLIMATE_DRAFT_MODES:
        raise ClimateSetupViolation("climate draft mode is invalid")
    room_values = values["rooms"]
    if (
        not isinstance(room_values, list)
        or not 1 <= len(room_values) <= MAX_CLIMATE_DRAFT_ROOMS
    ):
        raise ClimateSetupViolation("climate draft rooms are invalid")

    rooms_payload = climate_available_rooms(registry, snapshot)
    available_rooms = {
        room["id"]: room
        for room in rooms_payload["rooms"]  # type: ignore[index]
        if room["selectable"] is True
    }
    candidates = candidates_payload["candidates"]
    candidate_by_id = {
        candidate["candidate_id"]: candidate for candidate in candidates  # type: ignore[union-attr]
    }
    selected_room_ids: set[str] = set()
    selected_candidate_ids: set[str] = set()
    normalized_rooms: list[dict[str, object]] = []
    total_devices = 0
    device_type_names = public_climate_display_names()["device_kinds"]

    for room_value in room_values:
        room = _exact_mapping(
            room_value,
            _CLIMATE_DRAFT_ROOM_FIELDS,
            "climate draft room",
        )
        room_id = room["room_id"]
        if not isinstance(room_id, str) or room_id not in available_rooms:
            raise ClimateSetupViolation("climate draft room is unavailable")
        if room_id in selected_room_ids:
            raise ClimateSetupViolation("climate draft room is repeated")
        selected_room_ids.add(room_id)
        try:
            targets = climate_room_parameters(
                {
                    "target_temperature": room["target_temperature"],
                    "target_humidity": room["target_humidity"],
                    "strategy": room["strategy"],
                }
            )
        except ContourRegistryViolation as error:
            raise ClimateSetupViolation(str(error)) from error

        device_values = room["devices"]
        if not isinstance(device_values, list) or not device_values:
            raise ClimateSetupViolation("climate draft room needs devices")
        total_devices += len(device_values)
        if total_devices > MAX_CLIMATE_DRAFT_DEVICES:
            raise ClimateSetupViolation("climate draft has too many devices")
        normalized_devices: list[dict[str, object]] = []
        for device_value in device_values:
            device = _exact_mapping(
                device_value,
                _CLIMATE_DRAFT_DEVICE_FIELDS,
                "climate draft device",
            )
            candidate_id = device["candidate_id"]
            selected_type = device["type"]
            if not isinstance(candidate_id, str):
                raise ClimateSetupViolation("climate draft candidate is invalid")
            if candidate_id in selected_candidate_ids:
                raise ClimateSetupViolation("climate draft candidate is repeated")
            candidate = candidate_by_id.get(candidate_id)
            if candidate is None or candidate["selectable"] is not True:
                raise ClimateSetupViolation("climate draft candidate is unavailable")
            if candidate["room_id"] != room_id:
                raise ClimateSetupViolation("climate draft candidate room differs")
            if (
                not isinstance(selected_type, str)
                or selected_type not in candidate["suggested_types"]
            ):
                raise ClimateSetupViolation("climate draft device type is invalid")
            selected_candidate_ids.add(candidate_id)
            normalized_devices.append(
                {
                    "candidate_id": candidate_id,
                    "name": candidate["name"],
                    "type": selected_type,
                    "type_name": device_type_names[selected_type],
                }
            )

        normalized_rooms.append(
            {
                "id": room_id,
                "name": available_rooms[room_id]["name"],
                "targets": targets,
                "devices": sorted(
                    normalized_devices,
                    key=lambda item: item["candidate_id"],  # type: ignore[return-value]
                ),
            }
        )

    normalized_rooms.sort(key=lambda room: room["id"])  # type: ignore[arg-type]
    draft_values = {
        "snapshot_revision": current_revision,
        "name": name,
        "mode": mode,
        "rooms": normalized_rooms,
    }
    return {
        "contract": {
            "name": CLIMATE_DRAFT_CONTRACT_NAME,
            "version": CLIMATE_DRAFT_CONTRACT_VERSION,
        },
        "generated_at": snapshot.generated_at,
        "snapshot_revision": current_revision,
        "draft_revision": _json_safe_revision(draft_values),
        "status": "created",
        "save_allowed": False,
        "validation_required": True,
        "display_names": {
            "modes": dict(_DRAFT_MODE_NAMES),
            "strategies": dict(_DRAFT_STRATEGY_NAMES),
        },
        "name": name,
        "mode": mode,
        "rooms": normalized_rooms,
        "summary": {
            "room_count": len(normalized_rooms),
            "device_count": total_devices,
        },
    }


def climate_setup_options(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> dict[str, object]:
    """Return everything an admin form needs to create a safe draft."""

    rooms_payload = climate_available_rooms(registry, snapshot)
    candidates_payload = climate_device_candidates(registry, snapshot)
    suggestions_payload = climate_room_suggestions(registry, snapshot)
    suggestions = {
        suggestion["candidate_id"]: suggestion
        for suggestion in suggestions_payload["suggestions"]  # type: ignore[index]
    }
    devices: list[dict[str, object]] = []
    for candidate in candidates_payload["candidates"]:  # type: ignore[index]
        suggestion = suggestions[candidate["candidate_id"]]
        devices.append(
            {
                "candidate_id": candidate["candidate_id"],
                "name": candidate["name"],
                "room_id": candidate["room_id"],
                "suggested_types": candidate["suggested_types"],
                "recommended_type": candidate["recommended_type"],
                "status": candidate["status"],
                "suggested_room_id": suggestion["suggested_room_id"],
                "suggested_room_name": suggestion["suggested_room_name"],
                "reason": suggestion["reason"],
                "can_add": suggestion["can_accept"],
            }
        )

    return {
        "contract": {
            "name": CLIMATE_SETUP_OPTIONS_CONTRACT_NAME,
            "version": CLIMATE_SETUP_OPTIONS_CONTRACT_VERSION,
        },
        "generated_at": candidates_payload["generated_at"],
        "snapshot_revision": candidates_payload["snapshot_revision"],
        "data_status": candidates_payload["data_status"],
        "draft_creation_allowed": any(device["can_add"] is True for device in devices),
        "display_names": {
            "room_status": dict(_ROOM_STATUS_NAMES),
            "device_types": dict(
                candidates_payload["display_names"]["device_types"]  # type: ignore[index]
            ),
            "device_status": dict(_CANDIDATE_STATUS_NAMES),
            "suggestion_reasons": dict(_SUGGESTION_REASON_NAMES),
            "modes": dict(_DRAFT_MODE_NAMES),
            "strategies": dict(_DRAFT_STRATEGY_NAMES),
        },
        "rooms": [
            {
                "id": room["id"],
                "name": room["name"],
                "status": room["status"],
                "selectable": room["selectable"],
            }
            for room in rooms_payload["rooms"]  # type: ignore[index]
        ],
        "devices": devices,
    }


def _ordered_candidate_source_ids(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> tuple[str, ...]:
    """Keep response-local candidate references and private resolution identical."""

    configured = {device.source_id: device for device in registry.devices}
    imported = {device.source_id: device for device in snapshot.devices}
    source_ids = configured.keys() | imported.keys()
    if len(source_ids) > MAX_CLIMATE_DEVICE_CANDIDATES:
        raise ValueError("too many climate device candidates")

    def sort_key(source_id: str) -> tuple[str, str, str]:
        configured_device = configured.get(source_id)
        imported_device = imported.get(source_id)
        room_id = (
            configured_device.room_id
            if configured_device is not None
            else imported_device.room_id  # type: ignore[union-attr]
        )
        name = (
            configured_device.name
            if configured_device is not None
            else imported_device.name  # type: ignore[union-attr]
        )
        return (room_id, name.casefold(), source_id)

    return tuple(sorted(source_ids, key=sort_key))


def _exact_mapping(
    value: object,
    fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ClimateSetupViolation(f"{label} fields are invalid")
    return value


def _json_safe_revision(value: object) -> int:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).digest()
    return int.from_bytes(digest[:8], "big") % (JSON_SAFE_INTEGER_MAXIMUM + 1)
