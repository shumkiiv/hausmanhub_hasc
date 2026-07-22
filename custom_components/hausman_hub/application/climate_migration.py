"""Safe migration of existing external climate settings into HausmanHub.

Roadmap item 37. A one-shot, explicit import from the retired external
climate module into an empty native contour. The module holds pure mapping
and validation logic; network access lives only in
`legacy_climate_reader.py`, and the options flow drives the steps.

Moved: room names, per-room comfort targets (copied to both day and night
profiles), and the engine mode (`auto`/`forced_auto_only` -> `managed`,
`manual` -> `disabled`). Never moved: live state, schedule, authority
readiness, evidence, history, the API address, or any network parameters.
Authority is rebuilt natively; a `managed` mode survives confirm only when
the native authority check passes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json

from ..domain.climate import (
    ClimateCapability,
    ClimateControlOwner,
    ClimateControlScope,
    ClimateDevice,
    ClimateDeviceKind,
    ClimateEndpoint,
    ClimateEndpointRole,
    ClimateRegistry,
    ClimateRoom,
)
from ..domain.contours import (
    ClimateComfortSettings,
    ClimateContourRoom,
    ClimateProfile,
    ClimateSchedule,
    ContourDefinition,
    ContourEngine,
    ContourKind,
    ContourMode,
    ContourRegistry,
    ClimateStrategy,
)
from .climate_discovery import ClimateImportSnapshot, ImportedClimateDevice
from .climate_native_setup import ClimateHaEntityCatalog, UNASSIGNED_CANDIDATE_ROOM

MIGRATION_CONTRACT_NAME = "hausman-hub-climate-migration"
MIGRATION_CONTRACT_VERSION = 1
MAX_MIGRATION_ROOMS = 32
MAX_MIGRATION_DEVICES = 128

_ACTIVE_DOMAINS = {
    ClimateDeviceKind.AIR_CONDITIONER: ("climate",),
    ClimateDeviceKind.RADIATOR_THERMOSTAT: ("climate",),
    ClimateDeviceKind.HUMIDIFIER: ("humidifier",),
    ClimateDeviceKind.FLOOR_HEATING: ("climate", "switch"),
}
_PASSIVE_DOMAINS = {
    ClimateDeviceKind.TEMPERATURE_SENSOR: ("sensor",),
    ClimateDeviceKind.HUMIDITY_SENSOR: ("sensor",),
}
_KIND_BY_DOMAIN = {
    "climate": (ClimateDeviceKind.AIR_CONDITIONER,),
    "humidifier": (ClimateDeviceKind.HUMIDIFIER,),
    "sensor": (
        ClimateDeviceKind.TEMPERATURE_SENSOR,
        ClimateDeviceKind.HUMIDITY_SENSOR,
    ),
}
_OBSERVATION_ROLES = {
    ClimateDeviceKind.TEMPERATURE_SENSOR: ClimateEndpointRole.TEMPERATURE,
    ClimateDeviceKind.HUMIDITY_SENSOR: ClimateEndpointRole.HUMIDITY,
}


class ClimateMigrationViolation(ValueError):
    """The migration input or one mapping is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ClimateMigrationRoomPlan:
    """One migrated room with its copied comfort profile."""

    room_id: str
    name: str
    target_temperature: float
    target_humidity: int
    strategy: str


@dataclass(frozen=True, slots=True)
class ClimateMigrationDevicePlan:
    """One legacy device awaiting an explicit entity mapping."""

    legacy_source_id: str
    name: str
    room_id: str
    domain: str
    suggested_kinds: tuple[str, ...]
    command_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClimateMigrationPreview:
    """Everything the confirmation step must show before any write."""

    contract: dict[str, object]
    generated_at: int
    rooms: tuple[ClimateMigrationRoomPlan, ...]
    devices: tuple[ClimateMigrationDevicePlan, ...]
    mode_by_room: dict[str, str]
    mode_losses: tuple[str, ...]
    not_migrated: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClimateMigrationMapping:
    """One confirmed one-to-one legacy-to-entity assignment."""

    legacy_source_id: str
    entity_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class ClimateMigrationReceipt:
    """The bounded record of one finished migration for a safe rollback."""

    contract: dict[str, object]
    fingerprint: str
    created_device_ids: tuple[str, ...]
    created_room_ids: tuple[str, ...]
    mode: str


def build_migration_preview(
    snapshot: ClimateImportSnapshot,
) -> ClimateMigrationPreview:
    """Reduce one legacy state snapshot to an explicit migration preview."""

    if not isinstance(snapshot, ClimateImportSnapshot):
        raise ClimateMigrationViolation("a validated legacy snapshot is required")
    if not snapshot.runtime_fresh:
        raise ClimateMigrationViolation("legacy climate state is stale")
    rooms = tuple(
        sorted(
            (
                ClimateMigrationRoomPlan(
                    room_id=room.room_id,
                    name=room.name,
                    target_temperature=_required_number(
                        room.target_temperature, f"room {room.room_id} temperature"
                    ),
                    target_humidity=_required_humidity(room),
                    strategy=_required_strategy(room),
                )
                for room in snapshot.rooms
            ),
            key=lambda room: room.room_id,
        )
    )
    if not rooms or len(rooms) > MAX_MIGRATION_ROOMS:
        raise ClimateMigrationViolation("legacy room count is unsupported")
    devices = tuple(
        sorted(
            (
                ClimateMigrationDevicePlan(
                    legacy_source_id=device.source_id,
                    name=device.name,
                    room_id=device.room_id,
                    domain=device.domain,
                    suggested_kinds=tuple(
                        kind.value for kind in device.suggested_kinds
                    ),
                    command_types=device.command_types,
                )
                for device in snapshot.devices
            ),
            key=lambda device: (device.room_id, device.name.casefold(), device.legacy_source_id),
        )
    )
    if len(devices) > MAX_MIGRATION_DEVICES:
        raise ClimateMigrationViolation("legacy device count is unsupported")
    room_ids = {room.room_id for room in rooms}
    if any(device.room_id not in room_ids for device in devices):
        raise ClimateMigrationViolation("a legacy device references an unknown room")
    mode_by_room: dict[str, str] = {}
    mode_losses: list[str] = []
    for room in snapshot.rooms:
        mapped = _map_mode(room.mode)
        mode_by_room[room.room_id] = mapped
        if room.mode == "forced_auto_only":
            mode_losses.append(
                f"{room.name}: принудительный автоматический режим станет обычным управлением"
            )
        elif room.mode not in {"auto", "manual", "forced_auto_only", None}:
            raise ClimateMigrationViolation(
                f"legacy room mode is unsupported: {room.mode!r}"
            )
    return ClimateMigrationPreview(
        contract={
            "name": MIGRATION_CONTRACT_NAME,
            "version": MIGRATION_CONTRACT_VERSION,
        },
        generated_at=snapshot.generated_at,
        rooms=rooms,
        devices=devices,
        mode_by_room=mode_by_room,
        mode_losses=tuple(mode_losses),
        not_migrated=(
            "текущее состояние комнат и устройств",
            "расписание (старое API его не отдаёт)",
            "готовность authority (пересчитывается нативно)",
            "история и доказательства",
            "адрес старого API",
        ),
    )


def build_migrated_setup(
    preview: ClimateMigrationPreview,
    mappings: tuple[ClimateMigrationMapping, ...],
    catalog: ClimateHaEntityCatalog,
) -> tuple[ClimateRegistry, ContourRegistry, ClimateMigrationReceipt]:
    """Build the atomic registry, contour, and receipt from confirmed mappings."""

    if not isinstance(preview, ClimateMigrationPreview):
        raise ClimateMigrationViolation("a validated migration preview is required")
    if not isinstance(catalog, ClimateHaEntityCatalog):
        raise ClimateMigrationViolation("a validated entity catalog is required")
    mapping_by_source = _validate_mappings(preview, mappings, catalog)
    rooms = tuple(
        ClimateRoom(room_id=room.room_id, name=room.name) for room in preview.rooms
    )
    devices = tuple(
        _migrated_device(plan, mapping_by_source, catalog, preview.mode_by_room)
        for plan in preview.devices
        if plan.legacy_source_id in mapping_by_source
    )
    registry = ClimateRegistry(rooms=rooms, devices=devices)
    contour_rooms = tuple(
        ClimateContourRoom(
            room_id=room.room_id,
            device_ids=tuple(
                device.device_id
                for device in devices
                if device.room_id == room.room_id
            ),
            day_profile=ClimateComfortSettings(
                target_temperature=room.target_temperature,
                target_humidity=room.target_humidity,
                strategy=ClimateStrategy(room.strategy),
            ),
            night_profile=ClimateComfortSettings(
                target_temperature=room.target_temperature,
                target_humidity=room.target_humidity,
                strategy=ClimateStrategy(room.strategy),
            ),
            active_profile=ClimateProfile.DAY,
        )
        for room in preview.rooms
    )
    contour_mode = (
        ContourMode.AUTOMATIC
        if any(mode == "managed" for mode in preview.mode_by_room.values())
        else ContourMode.DISABLED
    )
    contour = ContourDefinition(
        contour_id="climate",
        name="Климат",
        kind=ContourKind.CLIMATE,
        mode=contour_mode,
        engine=ContourEngine.EXISTING_CLIMATE_CORE,
        rooms=contour_rooms,
        schedule=ClimateSchedule(enabled=False, day_start="07:00", night_start="23:00"),
    )
    contour_registry = ContourRegistry(contours=(contour,))
    fingerprint = _state_fingerprint(registry, contour_registry)
    receipt = ClimateMigrationReceipt(
        contract={
            "name": f"{MIGRATION_CONTRACT_NAME}-receipt",
            "version": MIGRATION_CONTRACT_VERSION,
        },
        fingerprint=fingerprint,
        created_device_ids=tuple(device.device_id for device in devices),
        created_room_ids=tuple(room.room_id for room in rooms),
        mode=contour_mode.value,
    )
    return registry, contour_registry, receipt


def _validate_mappings(
    preview: ClimateMigrationPreview,
    mappings: tuple[ClimateMigrationMapping, ...],
    catalog: ClimateHaEntityCatalog,
) -> dict[str, ClimateMigrationMapping]:
    known_sources = {device.legacy_source_id for device in preview.devices}
    mapping_by_source: dict[str, ClimateMigrationMapping] = {}
    used_entities: set[str] = set()
    for mapping in mappings:
        if mapping.legacy_source_id not in known_sources:
            raise ClimateMigrationViolation(
                f"mapping references an unknown legacy device: {mapping.legacy_source_id!r}"
            )
        if mapping.legacy_source_id in mapping_by_source:
            raise ClimateMigrationViolation(
                f"legacy device mapped twice: {mapping.legacy_source_id!r}"
            )
        try:
            kind = ClimateDeviceKind(mapping.kind)
        except (TypeError, ValueError) as error:
            raise ClimateMigrationViolation(
                f"mapping kind is unsupported: {mapping.kind!r}"
            ) from error
        entry = catalog.entry(mapping.entity_id)
        if entry is None:
            raise ClimateMigrationViolation(
                f"mapping entity is absent from Home Assistant: {mapping.entity_id!r}"
            )
        if not entry.available:
            raise ClimateMigrationViolation(
                f"mapping entity is unavailable: {mapping.entity_id!r}"
            )
        _validate_entity_kind(entry.domain, kind, mapping)
        if mapping.entity_id in used_entities:
            raise ClimateMigrationViolation(
                f"one entity cannot serve two devices: {mapping.entity_id!r}"
            )
        mapping_by_source[mapping.legacy_source_id] = mapping
        used_entities.add(mapping.entity_id)
    active_sources = {
        device.legacy_source_id
        for device in preview.devices
        if device.domain != "sensor"
    }
    missing = active_sources - set(mapping_by_source)
    if missing:
        raise ClimateMigrationViolation(
            "every active legacy device needs an explicit mapping or exclusion: "
            + ", ".join(sorted(missing))
        )
    return mapping_by_source


def _validate_entity_kind(
    domain: str,
    kind: ClimateDeviceKind,
    mapping: ClimateMigrationMapping,
) -> None:
    if kind in _ACTIVE_DOMAINS:
        if domain not in _ACTIVE_DOMAINS[kind]:
            raise ClimateMigrationViolation(
                f"entity domain {domain!r} cannot control kind {kind.value!r}"
            )
        return
    if domain not in _PASSIVE_DOMAINS[kind]:
        raise ClimateMigrationViolation(
            f"entity domain {domain!r} cannot observe kind {kind.value!r}"
        )


def _migrated_device(
    plan: ClimateMigrationDevicePlan,
    mapping_by_source: dict[str, ClimateMigrationMapping],
    catalog: ClimateHaEntityCatalog,
    mode_by_room: dict[str, str],
) -> ClimateDevice:
    mapping = mapping_by_source[plan.legacy_source_id]
    kind = ClimateDeviceKind(mapping.kind)
    active = kind in _ACTIVE_DOMAINS
    role = ClimateEndpointRole.CONTROL if active else _OBSERVATION_ROLES[kind]
    managed = mode_by_room.get(plan.room_id) == "managed" and active
    return ClimateDevice(
        device_id=_device_id(plan.room_id, kind, plan.legacy_source_id),
        name=plan.name,
        room_id=plan.room_id,
        kind=kind,
        source_id=f"hausmanhub-native-{mapping.entity_id}",
        control_scope=(
            ClimateControlScope.MANAGED if managed else ClimateControlScope.OBSERVED
        ),
        control_owner=(
            ClimateControlOwner.CLIMATE_CORE if managed else ClimateControlOwner.OBSERVED
        ),
        capabilities=_capabilities_for(kind, plan.command_types),
        endpoints=(ClimateEndpoint(role=role, entity_id=mapping.entity_id),),
    )


def _device_id(room_id: str, kind: ClimateDeviceKind, legacy_source_id: str) -> str:
    digest = hashlib.sha256(legacy_source_id.encode("utf-8")).hexdigest()[:8]
    return f"{room_id}_{kind.value}_{digest}"[:64]


def _capabilities_for(
    kind: ClimateDeviceKind,
    command_types: tuple[str, ...],
) -> tuple[ClimateCapability, ...]:
    commands = set(command_types)
    values: list[ClimateCapability] = []
    if kind is ClimateDeviceKind.AIR_CONDITIONER:
        if {"climate.set_hvac_mode", "climate.turn_off"}.issubset(commands):
            values.append(ClimateCapability.POWER)
        if "climate.set_temperature" in commands:
            values.append(ClimateCapability.TARGET_TEMPERATURE)
        if "climate.set_hvac_mode" in commands:
            values.append(ClimateCapability.HVAC_MODE)
        if "climate.set_fan_mode" in commands:
            values.append(ClimateCapability.FAN_MODE)
    elif kind is ClimateDeviceKind.HUMIDIFIER:
        if {"humidifier.turn_on", "humidifier.turn_off"}.issubset(commands):
            values.append(ClimateCapability.POWER)
        if "humidifier.set_humidity" in commands:
            values.append(ClimateCapability.TARGET_HUMIDITY)
    elif kind is ClimateDeviceKind.RADIATOR_THERMOSTAT:
        if {"trv.set_temperature", "climate.set_temperature"} & commands:
            values.append(ClimateCapability.TARGET_TEMPERATURE)
    elif kind is ClimateDeviceKind.FLOOR_HEATING:
        if "climate.set_temperature" in commands:
            values.append(ClimateCapability.TARGET_TEMPERATURE)
        if "switch.turn_on" in commands or "climate.turn_off" in commands:
            values.append(ClimateCapability.POWER)
    return tuple(values)


def _required_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClimateMigrationViolation(f"legacy {label} is missing")
    return float(value)


def _required_humidity(room: object) -> int:
    value = getattr(room, "target_humidity", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClimateMigrationViolation(
            f"legacy room {room.room_id} humidity is missing"
        )
    return int(value)


def _required_strategy(room: object) -> str:
    value = getattr(room, "target_strategy", None)
    if value not in {"soft", "normal", "aggressive"}:
        raise ClimateMigrationViolation(
            f"legacy room {room.room_id} strategy is unsupported: {value!r}"
        )
    return str(value)


def _map_mode(mode: str | None) -> str:
    if mode in {"auto", "forced_auto_only"}:
        return "managed"
    return "disabled"





def rollback_migrated_setup(
    registry: ClimateRegistry,
    contours: ContourRegistry,
    receipt: ClimateMigrationReceipt,
) -> tuple[ClimateRegistry, ContourRegistry]:
    """Remove the migrated setup only when nothing at all changed."""

    if not isinstance(receipt, ClimateMigrationReceipt):
        raise ClimateMigrationViolation("a validated migration receipt is required")
    if _state_fingerprint(registry, contours) != receipt.fingerprint:
        raise ClimateMigrationViolation(
            "migration rollback is blocked after manual changes"
        )
    return ClimateRegistry(), ContourRegistry()


def _state_fingerprint(
    registry: ClimateRegistry,
    contours: ContourRegistry,
) -> str:
    """Hash the complete registry and contour state for an exact rollback gate."""

    canonical = json.dumps(
        {
            "rooms": [
                (room.room_id, room.name, room.window_entity_id)
                for room in registry.rooms
            ],
            "devices": [
                (
                    device.device_id,
                    device.name,
                    device.room_id,
                    device.kind.value,
                    device.source_id,
                    device.control_scope.value,
                    device.control_owner.value,
                    [capability.value for capability in device.capabilities],
                    [
                        (endpoint.role.value, endpoint.entity_id)
                        for endpoint in device.endpoints
                    ],
                )
                for device in registry.devices
            ],
            "contours": [
                (
                    contour.contour_id,
                    contour.name,
                    contour.mode.value,
                    [
                        (
                            room.room_id,
                            room.active_profile.value,
                            room.day_profile.target_temperature,
                            room.day_profile.target_humidity,
                            room.day_profile.strategy.value,
                            room.night_profile.target_temperature,
                            room.night_profile.target_humidity,
                            room.night_profile.strategy.value,
                        )
                        for room in contour.rooms
                    ],
                    contour.schedule.enabled,
                )
                for contour in contours.contours
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
