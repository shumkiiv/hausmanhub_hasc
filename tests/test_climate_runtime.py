"""Pure orchestration tests with in-memory climate and storage adapters."""

from __future__ import annotations

import unittest

from custom_components.hausman_hub.application.climate_import import import_climate_state
from custom_components.hausman_hub.application.climate_registry import registry_from_payload
from custom_components.hausman_hub.application.climate_runtime import (
    ClimateRuntime,
    ClimateRuntimeUnavailable,
)
from custom_components.hausman_hub.domain.climate import ClimateRegistry
from custom_components.hausman_hub.domain.climate_bridge import (
    ClimateBridgeMode,
    climate_bridge_target,
)
from custom_components.hausman_hub.domain.configuration import SafeConfiguration
from tests.test_climate_import import registry_payload, source_payload


class MemoryStore:
    def __init__(self, registry: ClimateRegistry) -> None:
        self.registry = registry
        self.saved: list[ClimateRegistry] = []

    async def async_load(self) -> ClimateRegistry:
        return self.registry

    async def async_save(self, registry: ClimateRegistry) -> None:
        self.registry = registry
        self.saved.append(registry)


class MemoryBridge:
    def __init__(self) -> None:
        self.snapshot = import_climate_state(source_payload())
        self.fetch_count = 0
        self.executed = []

    async def async_fetch_state(self):
        self.fetch_count += 1
        return self.snapshot

    async def async_execute(self, plan):
        self.executed.append(plan)
        return {"ok": True}


def configuration(mode: ClimateBridgeMode) -> SafeConfiguration:
    return SafeConfiguration(
        mode="shadow",
        climate_bridge_mode=mode,
        climate_bridge_target=climate_bridge_target("http://127.0.0.1:1880"),
        climate_canary_room_id=(
            "living" if mode is ClimateBridgeMode.CANARY else None
        ),
    )


class ClimateRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_shadow_refreshes_but_never_posts(self) -> None:
        bridge = MemoryBridge()
        runtime = ClimateRuntime(
            entry_id="entry",
            configuration=configuration(ClimateBridgeMode.SHADOW),
            registry_store=MemoryStore(registry_from_payload(registry_payload())),
            bridge_client=bridge,
        )
        await runtime.async_start()

        result = await runtime.async_action(
            {
                "action": "set_room_target",
                "room_id": "living",
                "target_temperature": 24.5,
            }
        )

        self.assertEqual("shadow", result.status)
        self.assertEqual([], bridge.executed)
        self.assertGreaterEqual(bridge.fetch_count, 2)

    async def test_canary_posts_only_private_plan_and_returns_public_result(self) -> None:
        bridge = MemoryBridge()
        runtime = ClimateRuntime(
            entry_id="entry",
            configuration=configuration(ClimateBridgeMode.CANARY),
            registry_store=MemoryStore(registry_from_payload(registry_payload())),
            bridge_client=bridge,
        )
        await runtime.async_start()

        result = await runtime.async_action(
            {
                "action": "set_device_power",
                "device_id": "living_ac",
                "on": True,
            }
        )

        self.assertEqual("submitted", result.status)
        self.assertEqual("living_ac", result.device_id)
        self.assertEqual(1, len(bridge.executed))
        self.assertNotIn("deviceId", result.as_payload())

    async def test_registry_replacement_is_exact_and_persisted(self) -> None:
        store = MemoryStore(ClimateRegistry())
        runtime = ClimateRuntime(
            entry_id="entry",
            configuration=configuration(ClimateBridgeMode.SHADOW),
            registry_store=store,
            bridge_client=MemoryBridge(),
        )
        await runtime.async_start()

        result = await runtime.async_replace_registry(registry_payload())

        self.assertEqual(1, len(store.saved))
        self.assertEqual("living_ac", result["devices"][0]["id"])

    async def test_canary_cannot_change_registry_bindings(self) -> None:
        store = MemoryStore(registry_from_payload(registry_payload()))
        runtime = ClimateRuntime(
            entry_id="entry",
            configuration=configuration(ClimateBridgeMode.CANARY),
            registry_store=store,
            bridge_client=MemoryBridge(),
        )
        await runtime.async_start()

        with self.assertRaises(ClimateRuntimeUnavailable):
            await runtime.async_replace_registry(registry_payload())

        self.assertEqual([], store.saved)


if __name__ == "__main__":
    unittest.main()
