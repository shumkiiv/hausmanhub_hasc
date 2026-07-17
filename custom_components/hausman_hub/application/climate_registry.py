"""Persistence and shadow reconciliation use cases for the climate registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..domain.climate import (
    ClimateCapability,
    ClimateControlOwner,
    ClimateControlScope,
    ClimateDevice,
    ClimateDeviceKind,
    ClimateEndpoint,
    ClimateEndpointRole,
    ClimateModelViolation,
    ClimateRegistry,
    ClimateRoom,
    REGISTRY_VERSION,
)
from .climate_import import ClimateImportSnapshot


class ClimateRegistryViolation(ValueError):
    """Stored or submitted registry JSON does not match the exact contract."""


@dataclass(frozen=True, slots=True)
class ClimateRegistryReconciliation:
    """Read-only comparison; it never imports or deletes a binding itself."""

    matched_device_ids: tuple[str, ...]
    missing_device_ids: tuple[str, ...]
    room_mismatch_device_ids: tuple[str, ...]
    unregistered_source_ids: tuple[str, ...]

    @property
    def matches(self) -> bool:
        """Return whether every stored and imported device has exact parity."""

        return not (
            self.missing_device_ids
            or self.room_mismatch_device_ids
            or self.unregistered_source_ids
        )


def registry_to_payload(registry: ClimateRegistry) -> dict[str, object]:
    """Serialize only the fixed versioned registry shape."""

    return {
        "version": registry.version,
        "rooms": [
            {"id": room.room_id, "name": room.name} for room in registry.rooms
        ],
        "devices": [
            {
                "id": device.device_id,
                "name": device.name,
                "room_id": device.room_id,
                "kind": device.kind.value,
                "source_id": device.source_id,
                "control_scope": device.control_scope.value,
                "control_owner": device.control_owner.value,
                "capabilities": [value.value for value in device.capabilities],
                "endpoints": [
                    {"role": endpoint.role.value, "entity_id": endpoint.entity_id}
                    for endpoint in device.endpoints
                ],
            }
            for device in registry.devices
        ],
    }


def registry_from_payload(payload: object) -> ClimateRegistry:
    """Load an exact persisted/admin registry without permissive coercion."""

    root = _exact_mapping(payload, {"version", "rooms", "devices"}, "registry")
    if type(root["version"]) is not int or root["version"] != REGISTRY_VERSION:
        raise ClimateRegistryViolation("unsupported climate registry version")
    rooms = _bounded_list(root["rooms"], "registry rooms", 128)
    devices = _bounded_list(root["devices"], "registry devices", 512)
    try:
        return ClimateRegistry(
            version=root["version"],
            rooms=tuple(_room(value, index) for index, value in enumerate(rooms)),
            devices=tuple(
                _device(value, index) for index, value in enumerate(devices)
            ),
        )
    except (ClimateModelViolation, ValueError) as error:
        raise ClimateRegistryViolation(str(error)) from error


def reconcile_climate_registry(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
) -> ClimateRegistryReconciliation:
    """Compare exact private source bindings without modifying either side."""

    imported_by_source = {device.source_id: device for device in snapshot.devices}
    registered_sources = {device.source_id for device in registry.devices}
    matched: list[str] = []
    missing: list[str] = []
    room_mismatch: list[str] = []
    for device in registry.devices:
        imported = imported_by_source.get(device.source_id)
        if imported is None:
            missing.append(device.device_id)
        elif imported.room_id != device.room_id:
            room_mismatch.append(device.device_id)
        else:
            matched.append(device.device_id)
    return ClimateRegistryReconciliation(
        matched_device_ids=tuple(sorted(matched)),
        missing_device_ids=tuple(sorted(missing)),
        room_mismatch_device_ids=tuple(sorted(room_mismatch)),
        unregistered_source_ids=tuple(
            sorted(
                device.source_id
                for device in snapshot.devices
                if device.source_id not in registered_sources
            )
        ),
    )


def _room(value: object, index: int) -> ClimateRoom:
    item = _exact_mapping(value, {"id", "name"}, f"room {index}")
    return ClimateRoom(room_id=item["id"], name=item["name"])  # type: ignore[arg-type]


def _device(value: object, index: int) -> ClimateDevice:
    item = _exact_mapping(
        value,
        {
            "id",
            "name",
            "room_id",
            "kind",
            "source_id",
            "control_scope",
            "control_owner",
            "capabilities",
            "endpoints",
        },
        f"device {index}",
    )
    capabilities = _bounded_list(item["capabilities"], "device capabilities", 16)
    endpoints = _bounded_list(item["endpoints"], "device endpoints", 16)
    return ClimateDevice(
        device_id=item["id"],  # type: ignore[arg-type]
        name=item["name"],  # type: ignore[arg-type]
        room_id=item["room_id"],  # type: ignore[arg-type]
        kind=ClimateDeviceKind(item["kind"]),
        source_id=item["source_id"],  # type: ignore[arg-type]
        control_scope=ClimateControlScope(item["control_scope"]),
        control_owner=ClimateControlOwner(item["control_owner"]),
        capabilities=tuple(ClimateCapability(value) for value in capabilities),
        endpoints=tuple(_endpoint(value, endpoint_index) for endpoint_index, value in enumerate(endpoints)),
    )


def _endpoint(value: object, index: int) -> ClimateEndpoint:
    item = _exact_mapping(value, {"role", "entity_id"}, f"endpoint {index}")
    return ClimateEndpoint(
        role=ClimateEndpointRole(item["role"]),
        entity_id=item["entity_id"],  # type: ignore[arg-type]
    )


def _exact_mapping(
    value: object,
    keys: set[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ClimateRegistryViolation(f"{label} must be an object")
    if set(value) != keys:
        raise ClimateRegistryViolation(f"{label} must contain only its fixed fields")
    return value


def _bounded_list(value: object, label: str, maximum: int) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ClimateRegistryViolation(f"{label} must be a bounded list")
    return value
