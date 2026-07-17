"""Home Assistant form adapter for observation and typed rollout options.

The initial selector still chooses only an approved observation mode. Later
settings may explicitly arm one canary switch for one ``input_boolean`` helper
or configure the separate private Climate API bridge as disabled, shadow, or a
one-room canary. No generic service, token, route, proxy, or execution field is
accepted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .application.configuration import (
    CANARY_CONTROL_ENABLED_DEFAULT,
    CANARY_CONTROL_ENABLED_FIELD,
    CANARY_CONTROL_TARGET_FIELD,
    CLIMATE_BRIDGE_MODE_DEFAULT,
    CLIMATE_BRIDGE_MODE_FIELD,
    CLIMATE_BRIDGE_TARGET_FIELD,
    CLIMATE_CANARY_ROOM_ID_FIELD,
    ConfigurationViolation,
    LOCAL_SUMMARY_ENABLED_DEFAULT,
    LOCAL_SUMMARY_ENABLED_FIELD,
    MODE_FIELD,
    SUMMARY_UPDATE_INTERVAL_FIELD,
    create_initial_entry,
    create_options,
    effective_configuration,
)
from .const import DOMAIN, ENTRY_TITLE, ENTRY_UNIQUE_ID
from .domain.configuration import (
    APPROVED_MODES,
    APPROVED_SUMMARY_UPDATE_INTERVALS,
    READ_ONLY_MODE,
    SUMMARY_UPDATE_INTERVAL_DEFAULT,
)
from .domain.climate import ClimateModelViolation, ClimateRoom
from .domain.control import (
    INPUT_BOOLEAN_DOMAIN,
    UnsafeCanaryTargetError,
    canary_control_target,
)
from .domain.climate_bridge import (
    ClimateBridgeMode,
    UnsafeClimateBridgeTarget,
    climate_bridge_target,
)


MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[SelectOptionDict(value=mode, label=mode) for mode in APPROVED_MODES],
        translation_key="mode",
    )
)
SUMMARY_UPDATE_INTERVAL_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value=interval, label=interval)
            for interval in APPROVED_SUMMARY_UPDATE_INTERVALS
        ],
        translation_key="summary_update_interval",
    )
)
CANARY_CONTROL_TARGET_SELECTOR = EntitySelector(
    EntitySelectorConfig(domain=INPUT_BOOLEAN_DOMAIN, multiple=False)
)
CLIMATE_BRIDGE_MODE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[
            SelectOptionDict(value=mode.value, label=mode.value)
            for mode in ClimateBridgeMode
        ],
        translation_key="climate_bridge_mode",
    )
)


class StrictBooleanSelector(BooleanSelector):
    """Keep boolean choices exact instead of coercing truth-like values."""

    selector_type = "boolean"

    def __call__(self, value: object) -> bool:
        """Accept only the two actual boolean values at the form boundary."""

        if type(value) is not bool:
            raise vol.Invalid("setting must be true or false")
        return value


def _mode_schema(default: str) -> vol.Schema:
    return vol.Schema({vol.Required(MODE_FIELD, default=default): MODE_SELECTOR})


def _options_schema(
    mode_default: str,
    local_summary_enabled_default: bool,
    summary_update_interval_default: str,
    canary_control_enabled_default: bool,
    canary_control_target_default: str | None,
    climate_bridge_mode_default: str,
    climate_bridge_target_default: str | None,
    climate_canary_room_id_default: str | None,
) -> vol.Schema:
    """Show observation choices and the one narrow control-canary target."""

    fields: dict[vol.Marker, object] = {
        vol.Required(MODE_FIELD, default=mode_default): MODE_SELECTOR,
        vol.Required(
            LOCAL_SUMMARY_ENABLED_FIELD,
            default=local_summary_enabled_default,
        ): StrictBooleanSelector(),
        vol.Required(
            SUMMARY_UPDATE_INTERVAL_FIELD,
            default=summary_update_interval_default,
        ): SUMMARY_UPDATE_INTERVAL_SELECTOR,
        vol.Required(
            CANARY_CONTROL_ENABLED_FIELD,
            default=canary_control_enabled_default,
        ): StrictBooleanSelector(),
        vol.Required(
            CLIMATE_BRIDGE_MODE_FIELD,
            default=climate_bridge_mode_default,
        ): CLIMATE_BRIDGE_MODE_SELECTOR,
    }
    target_field = (
        vol.Optional(
            CANARY_CONTROL_TARGET_FIELD,
            default=canary_control_target_default,
        )
        if canary_control_target_default is not None
        else vol.Optional(CANARY_CONTROL_TARGET_FIELD)
    )
    fields[target_field] = CANARY_CONTROL_TARGET_SELECTOR
    bridge_target_field = (
        vol.Optional(
            CLIMATE_BRIDGE_TARGET_FIELD,
            default=climate_bridge_target_default,
        )
        if climate_bridge_target_default is not None
        else vol.Optional(CLIMATE_BRIDGE_TARGET_FIELD)
    )
    fields[bridge_target_field] = str
    canary_room_field = (
        vol.Optional(
            CLIMATE_CANARY_ROOM_ID_FIELD,
            default=climate_canary_room_id_default,
        )
        if climate_canary_room_id_default is not None
        else vol.Optional(CLIMATE_CANARY_ROOM_ID_FIELD)
    )
    fields[canary_room_field] = str
    return vol.Schema(fields)


def _safe_mode_default(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> str:
    """Return a safe form default only when all saved settings are safe."""

    try:
        return effective_configuration(entry_data, options).mode
    except ConfigurationViolation:
        return READ_ONLY_MODE


def _safe_local_summary_default(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> bool:
    """Keep an invalid saved setting from changing the visible page choice."""

    try:
        return effective_configuration(entry_data, options).local_summary_enabled
    except ConfigurationViolation:
        return LOCAL_SUMMARY_ENABLED_DEFAULT


def _safe_summary_update_interval_default(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> str:
    """Keep unsafe saved settings from selecting a refresh interval."""

    try:
        return effective_configuration(entry_data, options).summary_update_interval
    except ConfigurationViolation:
        return SUMMARY_UPDATE_INTERVAL_DEFAULT


def _safe_canary_control_enabled_default(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> bool:
    """Keep damaged saved settings from visibly arming the canary."""

    try:
        return effective_configuration(entry_data, options).canary_control_enabled
    except ConfigurationViolation:
        return CANARY_CONTROL_ENABLED_DEFAULT


def _safe_canary_control_target_default(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> str | None:
    """Expose a target default only for one completely valid armed canary."""

    try:
        target = effective_configuration(entry_data, options).canary_control_target
    except ConfigurationViolation:
        return None
    return None if target is None else target.entity_id


def _safe_climate_bridge_defaults(
    entry_data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[str, str | None, str | None]:
    """Return only completely validated bridge defaults to the options form."""

    try:
        configuration = effective_configuration(entry_data, options)
    except ConfigurationViolation:
        return CLIMATE_BRIDGE_MODE_DEFAULT, None, None
    target = configuration.climate_bridge_target
    return (
        configuration.climate_bridge_mode.value,
        None if target is None else target.origin,
        configuration.climate_canary_room_id,
    )


def _option_error_field(user_input: Mapping[str, Any]) -> str:
    """Point a rejected form value at the field that can safely explain it."""

    if user_input.get(MODE_FIELD) not in APPROVED_MODES:
        return MODE_FIELD
    if (
        LOCAL_SUMMARY_ENABLED_FIELD in user_input
        and type(user_input[LOCAL_SUMMARY_ENABLED_FIELD]) is not bool
    ):
        return LOCAL_SUMMARY_ENABLED_FIELD
    if (
        SUMMARY_UPDATE_INTERVAL_FIELD in user_input
        and user_input[SUMMARY_UPDATE_INTERVAL_FIELD]
        not in APPROVED_SUMMARY_UPDATE_INTERVALS
    ):
        return SUMMARY_UPDATE_INTERVAL_FIELD
    if (
        CANARY_CONTROL_ENABLED_FIELD in user_input
        and type(user_input[CANARY_CONTROL_ENABLED_FIELD]) is not bool
    ):
        return CANARY_CONTROL_ENABLED_FIELD
    if user_input.get(CANARY_CONTROL_ENABLED_FIELD) is True:
        try:
            canary_control_target(user_input.get(CANARY_CONTROL_TARGET_FIELD))
        except UnsafeCanaryTargetError:
            return CANARY_CONTROL_TARGET_FIELD
    bridge_mode = user_input.get(CLIMATE_BRIDGE_MODE_FIELD, CLIMATE_BRIDGE_MODE_DEFAULT)
    if bridge_mode not in {mode.value for mode in ClimateBridgeMode}:
        return CLIMATE_BRIDGE_MODE_FIELD
    if bridge_mode != ClimateBridgeMode.DISABLED.value:
        try:
            climate_bridge_target(user_input.get(CLIMATE_BRIDGE_TARGET_FIELD))
        except UnsafeClimateBridgeTarget:
            return CLIMATE_BRIDGE_TARGET_FIELD
    if bridge_mode == ClimateBridgeMode.CANARY.value:
        try:
            ClimateRoom(
                user_input.get(CLIMATE_CANARY_ROOM_ID_FIELD),  # type: ignore[arg-type]
                "Temporary",
            )
        except ClimateModelViolation:
            return CLIMATE_CANARY_ROOM_ID_FIELD
    return CANARY_CONTROL_TARGET_FIELD


class HausmanHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single safe HausMan Hub configuration entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> HausmanHubOptionsFlow:
        """Return the options flow without retaining mutable entry state."""

        return HausmanHubOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Accept only an approved non-executing mode."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = create_initial_entry(user_input.get(MODE_FIELD))
            except ConfigurationViolation:
                errors[MODE_FIELD] = "unsafe_mode"
            else:
                await self.async_set_unique_id(ENTRY_UNIQUE_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=ENTRY_TITLE, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_mode_schema(READ_ONLY_MODE),
            errors=errors,
        )


class HausmanHubOptionsFlow(config_entries.OptionsFlow):
    """Edit observation settings and the opt-in input-boolean canary."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Keep future options within the validated canary boundary."""

        mode_default = _safe_mode_default(self.config_entry.data, self.config_entry.options)
        local_summary_enabled_default = _safe_local_summary_default(
            self.config_entry.data,
            self.config_entry.options,
        )
        summary_update_interval_default = _safe_summary_update_interval_default(
            self.config_entry.data,
            self.config_entry.options,
        )
        canary_control_enabled_default = _safe_canary_control_enabled_default(
            self.config_entry.data,
            self.config_entry.options,
        )
        canary_control_target_default = _safe_canary_control_target_default(
            self.config_entry.data,
            self.config_entry.options,
        )
        (
            climate_bridge_mode_default,
            climate_bridge_target_default,
            climate_canary_room_id_default,
        ) = _safe_climate_bridge_defaults(
            self.config_entry.data,
            self.config_entry.options,
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                options = create_options(
                    user_input.get(MODE_FIELD),
                    user_input.get(
                        LOCAL_SUMMARY_ENABLED_FIELD,
                        local_summary_enabled_default,
                    ),
                    user_input.get(
                        SUMMARY_UPDATE_INTERVAL_FIELD,
                        summary_update_interval_default,
                    ),
                    user_input.get(
                        CANARY_CONTROL_ENABLED_FIELD,
                        canary_control_enabled_default,
                    ),
                    user_input.get(
                        CANARY_CONTROL_TARGET_FIELD,
                        canary_control_target_default,
                    ),
                    user_input.get(
                        CLIMATE_BRIDGE_MODE_FIELD,
                        climate_bridge_mode_default,
                    ),
                    user_input.get(
                        CLIMATE_BRIDGE_TARGET_FIELD,
                        climate_bridge_target_default,
                    ),
                    user_input.get(
                        CLIMATE_CANARY_ROOM_ID_FIELD,
                        climate_canary_room_id_default,
                    ),
                )
            except ConfigurationViolation:
                error_field = _option_error_field(user_input)
                if error_field == MODE_FIELD:
                    errors[error_field] = "unsafe_mode"
                elif error_field == LOCAL_SUMMARY_ENABLED_FIELD:
                    errors[error_field] = "unsafe_local_summary_setting"
                elif error_field == SUMMARY_UPDATE_INTERVAL_FIELD:
                    errors[error_field] = "unsafe_summary_update_interval"
                elif error_field == CANARY_CONTROL_ENABLED_FIELD:
                    errors[error_field] = "unsafe_canary_control_setting"
                elif error_field == CLIMATE_BRIDGE_MODE_FIELD:
                    errors[error_field] = "unsafe_climate_bridge_mode"
                elif error_field == CLIMATE_BRIDGE_TARGET_FIELD:
                    errors[error_field] = "unsafe_climate_bridge_target"
                elif error_field == CLIMATE_CANARY_ROOM_ID_FIELD:
                    errors[error_field] = "unsafe_climate_canary_room"
                else:
                    errors[error_field] = "unsafe_canary_control_target"
            else:
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                mode_default,
                local_summary_enabled_default,
                summary_update_interval_default,
                canary_control_enabled_default,
                canary_control_target_default,
                climate_bridge_mode_default,
                climate_bridge_target_default,
                climate_canary_room_id_default,
            ),
            errors=errors,
        )
