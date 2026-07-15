"""Home Assistant boundary for the read-only HausMan Hub integration.

It creates only nine diagnostic count sensors from the approved aggregate
summary. It has no services, device connections, or execution routes, and its
separate local view remains authenticated and GET-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .application.configuration import ConfigurationViolation, effective_configuration

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load the safe count display without acquiring runtime authority."""

    try:
        effective_configuration(entry.data, entry.options)
    except ConfigurationViolation:
        return False

    # Imports stay at the outer boundary so framework-independent tests can run
    # without Home Assistant itself.
    from homeassistant.const import Platform

    from .local_summary import register_local_summary_access

    await hass.config_entries.async_forward_entry_setups(entry, (Platform.SENSOR,))
    register_local_summary_access(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the count display and make its local summary unavailable."""

    from homeassistant.const import Platform

    from .local_summary import clear_local_summary_access

    unloaded = await hass.config_entries.async_unload_platforms(entry, (Platform.SENSOR,))
    if unloaded:
        clear_local_summary_access(hass, entry)
    return unloaded
