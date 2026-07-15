"""Home Assistant adapter for a redacted, allow-list diagnostics snapshot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .application.configuration import ConfigurationViolation, effective_configuration
from .application.diagnostics import (
    diagnostics_snapshot_for_configuration,
    unavailable_diagnostics_snapshot,
)
from .home_observation import collect_home_summary

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    """Return counts only for the one active safe HASC setup."""

    active_entry = _single_loaded_entry(hass, entry)
    if active_entry is None:
        return unavailable_diagnostics_snapshot()

    try:
        configuration = effective_configuration(active_entry.data, active_entry.options)
    except ConfigurationViolation:
        return unavailable_diagnostics_snapshot()

    return diagnostics_snapshot_for_configuration(
        configuration,
        collect_home_summary(hass, active_entry.entry_id),
    )


def _single_loaded_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> ConfigEntry | None:
    """Return the one saved HASC entry only when it is currently loaded."""

    saved_entries = hass.config_entries.async_entries(entry.domain)
    if len(saved_entries) != 1:
        return None
    saved_entry = saved_entries[0]
    if saved_entry.entry_id != entry.entry_id:
        return None
    if not any(
        loaded_entry.entry_id == saved_entry.entry_id
        for loaded_entry in hass.config_entries.async_loaded_entries(entry.domain)
    ):
        return None
    return saved_entry
