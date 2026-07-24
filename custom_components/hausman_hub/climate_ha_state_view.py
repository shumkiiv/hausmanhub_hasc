"""Home Assistant state view for the native climate observation adapter."""

from __future__ import annotations

import hashlib
import importlib
import re
from typing import TYPE_CHECKING

from .application.climate_ha_observations import (
    MAX_STATE_LENGTH,
    ClimateHaEntityState,
)
from .application.climate_native_setup import (
    CLIMATE_HA_CATALOG_DOMAINS,
    CLIMATE_HA_SENSOR_DEVICE_CLASSES,
    ClimateHaCatalogEntry,
    ClimateHaCatalogRoom,
    ClimateHaEntityCatalog,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_OBSERVED_ATTRIBUTES = frozenset(
    {
        "hvac_action",
        "temperature",
        "current_temperature",
        "fan_mode",
        "humidity",
    }
)
_STABLE_ROOM_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class HomeAssistantClimateStateView:
    """Expose bounded immutable entity states to the native adapter."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def entity_state(self, entity_id: str) -> ClimateHaEntityState | None:
        """Return one current bounded state, or None when it cannot be used."""

        state = self._hass.states.get(entity_id)
        if state is None or len(state.state) > MAX_STATE_LENGTH:
            return None
        attributes = {
            key: value
            for key, value in state.attributes.items()
            if key in _OBSERVED_ATTRIBUTES
            and type(value) in {str, int, float, bool}
        }
        return ClimateHaEntityState(
            entity_id=entity_id,
            state=state.state,
            attributes=attributes,
            last_updated_ms=int(state.last_updated.timestamp() * 1000),
        )

    def entity_catalog(self) -> ClimateHaEntityCatalog:
        """Enumerate climate-relevant entities for native setup discovery."""

        states = []
        for state in self._hass.states.async_all():
            domain = state.entity_id.split(".", 1)[0]
            if domain not in CLIMATE_HA_CATALOG_DOMAINS:
                continue
            device_class = state.attributes.get("device_class")
            if (
                domain == "sensor"
                and device_class not in CLIMATE_HA_SENSOR_DEVICE_CLASSES
            ):
                continue
            if len(state.state) > MAX_STATE_LENGTH:
                continue
            states.append(state)
        rooms, entity_rooms = self._room_catalog(
            tuple(state.entity_id for state in states)
        )
        entries: list[ClimateHaCatalogEntry] = []
        for state in states:
            domain = state.entity_id.split(".", 1)[0]
            device_class = state.attributes.get("device_class")
            supported_features = state.attributes.get("supported_features")
            friendly_name = state.attributes.get("friendly_name")
            entries.append(
                ClimateHaCatalogEntry(
                    entity_id=state.entity_id,
                    domain=domain,
                    state=state.state,
                    device_class=(
                        device_class if isinstance(device_class, str) else None
                    ),
                    supported_features=(
                        supported_features
                        if type(supported_features) is int
                        and supported_features >= 0
                        else 0
                    ),
                    friendly_name=(
                        friendly_name if isinstance(friendly_name, str) else None
                    ),
                    available=state.state not in {"", "unavailable", "unknown"},
                    last_updated_ms=int(state.last_updated.timestamp() * 1000),
                    room_id=entity_rooms.get(
                        state.entity_id,
                        "",
                    ),
                )
            )
        return ClimateHaEntityCatalog(
            entries=tuple(
                sorted(entries, key=lambda entry: entry.entity_id)
            ),
            rooms=rooms,
        )

    def _room_catalog(
        self,
        entity_ids: tuple[str, ...],
    ) -> tuple[tuple[ClimateHaCatalogRoom, ...], dict[str, str]]:
        """Resolve HA areas and inherited entity/device assignments read-only."""

        try:
            area_module = importlib.import_module(
                "homeassistant.helpers.area_registry"
            )
            device_module = importlib.import_module(
                "homeassistant.helpers.device_registry"
            )
            entity_module = importlib.import_module(
                "homeassistant.helpers.entity_registry"
            )
        except ModuleNotFoundError:
            # The pure unit-test environment intentionally has no HA package.
            return (), {}

        area_registry = area_module.async_get(self._hass)
        device_registry = device_module.async_get(self._hass)
        entity_registry = entity_module.async_get(self._hass)
        area_entries = sorted(
            area_registry.async_list_areas(),
            key=lambda area: area.id,
        )
        area_room_ids: dict[str, str] = {}
        rooms: list[ClimateHaCatalogRoom] = []
        used_room_ids: set[str] = set()
        for area in area_entries:
            source_area_id = str(area.id)
            room_id = _stable_area_room_id(source_area_id, used_room_ids)
            used_room_ids.add(room_id)
            area_room_ids[source_area_id] = room_id
            rooms.append(
                ClimateHaCatalogRoom(
                    room_id=room_id,
                    name=_bounded_area_name(area.name, room_id),
                )
            )

        entity_rooms: dict[str, str] = {}
        for entity_id in entity_ids:
            registry_entry = entity_registry.async_get(entity_id)
            if registry_entry is None:
                continue
            source_area_id = registry_entry.area_id
            if not source_area_id and registry_entry.device_id:
                device_entry = device_registry.async_get(registry_entry.device_id)
                source_area_id = (
                    None if device_entry is None else device_entry.area_id
                )
            room_id = area_room_ids.get(source_area_id)
            if room_id is not None:
                entity_rooms[entity_id] = room_id

        return tuple(rooms), entity_rooms

    def signal_entity_catalog(
        self,
        allowed_domains: frozenset[str],
    ) -> ClimateHaEntityCatalog:
        """Enumerate only entities usable for one signal binding selection."""

        entries: list[ClimateHaCatalogEntry] = []
        for state in self._hass.states.async_all():
            domain = state.entity_id.split(".", 1)[0]
            if domain not in allowed_domains:
                continue
            if len(state.state) > MAX_STATE_LENGTH:
                continue
            friendly_name = state.attributes.get("friendly_name")
            entries.append(
                ClimateHaCatalogEntry(
                    entity_id=state.entity_id,
                    domain=domain,
                    state=state.state,
                    device_class=None,
                    supported_features=0,
                    friendly_name=(
                        friendly_name if isinstance(friendly_name, str) else None
                    ),
                    available=state.state not in {"", "unavailable", "unknown"},
                    last_updated_ms=int(state.last_updated.timestamp() * 1000),
                )
            )
        return ClimateHaEntityCatalog(
            entries=tuple(
                sorted(entries, key=lambda entry: entry.entity_id)
            )
        )


def _stable_area_room_id(area_id: str, used: set[str]) -> str:
    """Keep normal HA area ids and derive a bounded stable fallback otherwise."""

    if _STABLE_ROOM_ID.fullmatch(area_id) and area_id not in used:
        return area_id
    attempt = 0
    while True:
        material = area_id if attempt == 0 else f"{area_id}:{attempt}"
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]
        candidate = f"ha_{digest}"
        if candidate not in used:
            return candidate
        attempt += 1


def _bounded_area_name(value: object, room_id: str) -> str:
    """Return a non-empty name accepted by the climate domain."""

    if isinstance(value, str):
        normalized = value.strip()[:120].rstrip()
        if normalized:
            return normalized
    return f"Комната {room_id}"[:120]
