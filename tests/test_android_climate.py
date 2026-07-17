"""Pure tests for the public tablet and private administrator projections."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from custom_components.hausman_hub.application.android_climate import (
    admin_climate_import_snapshot,
    android_climate_snapshot,
)
from custom_components.hausman_hub.application.climate_import import import_climate_state
from custom_components.hausman_hub.application.climate_registry import registry_from_payload
from tests.test_climate_import import registry_payload, source_payload


class AndroidClimateTest(unittest.TestCase):
    """Keep the normal Android contract stable and private-id free."""

    def test_tablet_snapshot_contains_registered_devices_and_live_room_state(self) -> None:
        result = android_climate_snapshot(
            registry_from_payload(registry_payload()),
            import_climate_state(source_payload()),
            commands_enabled=False,
        )

        self.assertEqual("hausman-hasc-home", result["contract"]["name"])
        self.assertEqual("living_ac", result["rooms"][0]["devices"][0]["id"])
        self.assertEqual(25.8, result["rooms"][0]["temperature"])
        self.assertFalse(result["climate"]["commands_enabled"])
        self.assertEqual(1, result["reconciliation"]["unregistered_device_count"])

    def test_tablet_snapshot_never_exposes_private_source_or_entity_ids(self) -> None:
        result = android_climate_snapshot(
            registry_from_payload(registry_payload()),
            import_climate_state(source_payload()),
            commands_enabled=True,
        )
        encoded = json.dumps(result, sort_keys=True)

        self.assertNotIn("synthetic-ac-source-living", encoded)
        self.assertNotIn("climate.synthetic_living_ac", encoded)
        self.assertNotIn("source_id", encoded)
        self.assertNotIn("entity_id", encoded)

    def test_admin_import_explicitly_contains_candidates_and_private_bindings(self) -> None:
        result = admin_climate_import_snapshot(
            registry_from_payload(registry_payload()),
            import_climate_state(source_payload()),
        )

        self.assertEqual(
            "synthetic-humidifier-source-kids",
            result["candidates"][1]["source_id"],
        )
        self.assertEqual(
            ["humidifier"],
            result["candidates"][1]["suggested_kinds"],
        )


if __name__ == "__main__":
    unittest.main()
