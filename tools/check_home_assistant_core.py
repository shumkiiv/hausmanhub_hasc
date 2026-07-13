"""Run the HASC read-only skeleton against an isolated Home Assistant Core.

This is an explicit compatibility smoke check, not a live-home test. It copies
the integration into a new temporary Home Assistant configuration directory,
creates only a safe ``shadow`` config entry, and removes all temporary files
when finished. It never receives credentials, opens a network connection, or
calls Home Assistant services or devices.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from homeassistant import config_entries
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_SOURCE = REPOSITORY_ROOT / "custom_components" / "hausman_hub"


def load_integration_domain() -> str:
    """Read the tested integration's domain without importing its source."""

    manifest_path = INTEGRATION_SOURCE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest["domain"]


def assert_result(actual: Any, expected: Any, message: str) -> None:
    """Raise a clear error when a Home Assistant flow result is unsafe."""

    if actual != expected:
        raise RuntimeError(f"{message}: expected {expected!r}, got {actual!r}")


async def async_run_check() -> None:
    """Exercise setup, config flow, options flow, and unload in a blank Core."""

    domain = load_integration_domain()

    with tempfile.TemporaryDirectory(prefix="hasc-core-check-") as temporary_directory:
        config_directory = Path(temporary_directory)
        integration_target = config_directory / "custom_components" / domain
        integration_target.parent.mkdir(parents=True)
        shutil.copytree(INTEGRATION_SOURCE, integration_target)

        hass = HomeAssistant(str(config_directory))
        loader.async_setup(hass)
        hass.config.skip_pip = True
        configured_hass = await async_from_config_dict({}, hass)
        assert_result(
            configured_hass,
            hass,
            "empty Home Assistant configuration must bootstrap successfully",
        )
        await hass.async_start()
        try:
            await hass.async_block_till_done()

            rejected_proxy = await hass.config_entries.flow.async_init(
                domain,
                context={"source": config_entries.SOURCE_USER},
                data={"mode": "proxy"},
            )
            assert_result(rejected_proxy["type"], "form", "proxy must not create an entry")
            assert_result(
                rejected_proxy["errors"],
                {"mode": "unsafe_mode"},
                "proxy must be rejected",
            )

            created_entry = await hass.config_entries.flow.async_init(
                domain,
                context={"source": config_entries.SOURCE_USER},
                data={"mode": "shadow"},
            )
            assert_result(
                created_entry["type"],
                "create_entry",
                "shadow must create an entry",
            )
            entry = created_entry["result"]
            assert_result(entry.data["mode"], "shadow", "entry must preserve the safe mode")
            assert_result(
                entry.data["direct_execution_status"],
                "direct_execution_blocked",
                "direct execution must stay blocked",
            )
            await hass.async_block_till_done()
            assert_result(
                entry.state,
                config_entries.ConfigEntryState.LOADED,
                "safe entry must load successfully",
            )

            options_form = await hass.config_entries.options.async_init(entry.entry_id)
            assert_result(options_form["type"], "form", "options flow must show a form")
            safe_options = await hass.config_entries.options.async_configure(
                options_form["flow_id"],
                {"mode": "read-only"},
            )
            assert_result(
                safe_options["type"],
                "create_entry",
                "read-only must be accepted in options",
            )

            assert_result(
                hass.services.async_services().get(domain),
                None,
                "the integration must not register services",
            )
            assert_result(
                entity_registry.async_entries_for_config_entry(
                    entity_registry.async_get(hass),
                    entry.entry_id,
                ),
                [],
                "the integration must not create entities",
            )

            removal = await hass.config_entries.async_remove(entry.entry_id)
            assert_result(
                removal["require_restart"],
                False,
                "safe entry must unload and remove cleanly",
            )
            await hass.async_block_till_done()
        finally:
            await hass.async_stop()


def main() -> None:
    """Run the isolated Core compatibility check from a Python 3.14 environment."""

    asyncio.run(async_run_check())
    print("Home Assistant Core compatibility check passed.")


if __name__ == "__main__":
    main()
