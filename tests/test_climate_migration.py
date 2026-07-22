"""Pure tests for the safe legacy climate settings migration (item 37)."""

from __future__ import annotations

import unittest

from custom_components.hausman_hub.application.climate_migration import (
    ClimateMigrationMapping,
    ClimateMigrationViolation,
    build_migration_preview,
    build_migrated_setup,
)
from custom_components.hausman_hub.application.climate_native_setup import (
    ClimateHaCatalogEntry,
    ClimateHaEntityCatalog,
)
from custom_components.hausman_hub.domain.contours import ContourMode
from tests.climate_bridge_fixture import import_climate_state
from tests.test_climate_import import source_payload

NOW_MS = 1784280005000


def _snapshot():
    return import_climate_state(source_payload(), now_ms=NOW_MS)


def _catalog(*entries: ClimateHaCatalogEntry) -> ClimateHaEntityCatalog:
    return ClimateHaEntityCatalog(entries=tuple(entries))


def _ac_entry(**overrides) -> ClimateHaCatalogEntry:
    values = {
        "entity_id": "climate.living_ac",
        "domain": "climate",
        "state": "cool",
        "device_class": None,
        "supported_features": 137,
        "friendly_name": "Living AC",
        "available": True,
        "last_updated_ms": 1784280000000,
    }
    values.update(overrides)
    return ClimateHaCatalogEntry(**values)


def _humidifier_entry(**overrides) -> ClimateHaCatalogEntry:
    values = {
        "entity_id": "humidifier.kids",
        "domain": "humidifier",
        "state": "off",
        "device_class": None,
        "supported_features": 0,
        "friendly_name": "Kids humidifier",
        "available": True,
        "last_updated_ms": 1784280000000,
    }
    values.update(overrides)
    return ClimateHaCatalogEntry(**values)


def _mappings() -> tuple[ClimateMigrationMapping, ...]:
    return (
        ClimateMigrationMapping(
            legacy_source_id="synthetic-ac-source-living",
            entity_id="climate.living_ac",
            kind="air_conditioner",
            ),
        ClimateMigrationMapping(
            legacy_source_id="synthetic-humidifier-source-kids",
            entity_id="humidifier.kids",
            kind="humidifier",
        ),
    )


class MigrationPreviewTest(unittest.TestCase):
    """The preview reduces the legacy state to explicit migration choices."""

    def test_preview_copies_targets_modes_and_bounds_exclusions(self) -> None:
        preview = build_migration_preview(_snapshot())

        self.assertEqual(
            {"name": "hausman-hub-climate-migration", "version": 1},
            preview.contract,
        )
        self.assertEqual(
            [
                ("kids", 24.5, 50, "normal"),
                ("living", 25.0, 45, "normal"),
            ],
            [
                (room.room_id, room.target_temperature, room.target_humidity, room.strategy)
                for room in preview.rooms
            ],
        )
        self.assertEqual(
            {"living": "managed", "kids": "managed"}, preview.mode_by_room
        )
        self.assertEqual((), preview.mode_losses)
        self.assertIn("расписание (старое API его не отдаёт)", preview.not_migrated)
        self.assertEqual(
            [
                ("synthetic-humidifier-source-kids", "humidifier"),
                ("synthetic-ac-source-living", "climate"),
            ],
            [(device.legacy_source_id, device.domain) for device in preview.devices],
        )

    def test_stale_or_invalid_snapshot_fails_closed(self) -> None:
        stale = import_climate_state(source_payload(), now_ms=NOW_MS + 10 * 60 * 1000)
        with self.assertRaises(ClimateMigrationViolation):
            build_migration_preview(stale)
        with self.assertRaises(ClimateMigrationViolation):
            build_migration_preview(None)


class MigrationSetupTest(unittest.TestCase):
    """Confirmed mappings build the atomic registry, contour, and receipt."""

    def test_full_mapping_builds_native_setup(self) -> None:
        preview = build_migration_preview(_snapshot())
        registry, contours, receipt = build_migrated_setup(
            preview,
            _mappings(),
            _catalog(_ac_entry(), _humidifier_entry()),
        )

        self.assertEqual(["kids", "living"], [room.room_id for room in registry.rooms])
        devices = {device.source_id: device for device in registry.devices}
        self.assertEqual(
            {
                "hausmanhub-native-climate.living_ac",
                "hausmanhub-native-humidifier.kids",
            },
            set(devices),
        )
        ac = devices["hausmanhub-native-climate.living_ac"]
        self.assertEqual("living", ac.room_id)
        self.assertEqual("climate.living_ac", ac.endpoints[0].entity_id)
        self.assertEqual("managed", ac.control_scope.value)
        humidifier = devices["hausmanhub-native-humidifier.kids"]
        self.assertEqual("kids", humidifier.room_id)
        self.assertEqual("humidifier.kids", humidifier.endpoints[0].entity_id)
        contour = contours.contour("climate")
        self.assertEqual(ContourMode.AUTOMATIC, contour.mode)
        self.assertFalse(contour.schedule.enabled)
        for room in contour.rooms:
            self.assertEqual(room.day_profile, room.night_profile)
        self.assertEqual(2, len(receipt.fingerprint and receipt.created_device_ids))
        self.assertEqual("automatic", receipt.mode)

    def test_missing_entity_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        mappings = (
            ClimateMigrationMapping(
                legacy_source_id="synthetic-ac-source-living",
                entity_id="climate.missing",
                kind="air_conditioner",
            ),
            _mappings()[1],
        )
        with self.assertRaisesRegex(ClimateMigrationViolation, "absent"):
            build_migrated_setup(preview, mappings, _catalog(_ac_entry(), _humidifier_entry()))

    def test_unavailable_entity_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        with self.assertRaisesRegex(ClimateMigrationViolation, "unavailable"):
            build_migrated_setup(
                preview,
                _mappings(),
                _catalog(_ac_entry(available=False, state="unavailable"), _humidifier_entry()),
            )

    def test_domain_mismatch_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        mappings = (
            ClimateMigrationMapping(
                legacy_source_id="synthetic-ac-source-living",
                entity_id="humidifier.kids",
                kind="air_conditioner",
            ),
            _mappings()[1],
        )
        with self.assertRaisesRegex(ClimateMigrationViolation, "cannot control"):
            build_migrated_setup(preview, mappings, _catalog(_ac_entry(), _humidifier_entry()))

    def test_shared_entity_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        mappings = (
            ClimateMigrationMapping(
                legacy_source_id="synthetic-ac-source-living",
                entity_id="climate.living_ac",
                kind="air_conditioner",
            ),
            ClimateMigrationMapping(
                legacy_source_id="synthetic-humidifier-source-kids",
                entity_id="climate.living_ac",
                kind="air_conditioner",
            ),
        )
        with self.assertRaisesRegex(ClimateMigrationViolation, "cannot serve two"):
            build_migrated_setup(preview, mappings, _catalog(_ac_entry(), _humidifier_entry()))

    def test_unmapped_active_device_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        with self.assertRaisesRegex(ClimateMigrationViolation, "explicit mapping"):
            build_migrated_setup(preview, _mappings()[:1], _catalog(_ac_entry()))

    def test_unknown_legacy_device_rejected(self) -> None:
        preview = build_migration_preview(_snapshot())
        mappings = _mappings() + (
            ClimateMigrationMapping(
                legacy_source_id="unknown-device",
                entity_id="climate.living_ac",
                kind="air_conditioner",
            ),
        )
        with self.assertRaisesRegex(ClimateMigrationViolation, "unknown legacy"):
            build_migrated_setup(preview, mappings, _catalog(_ac_entry(), _humidifier_entry()))


if __name__ == "__main__":
    unittest.main()


class MigrationRollbackTest(unittest.TestCase):
    """The safe rollback removes exactly the migrated objects."""

    def test_rollback_removes_only_migrated_objects(self) -> None:
        from custom_components.hausman_hub.application.climate_migration import (
            rollback_migrated_setup,
        )
        from custom_components.hausman_hub.domain.climate import ClimateRegistry
        from custom_components.hausman_hub.domain.contours import ContourRegistry

        preview = build_migration_preview(_snapshot())
        registry, contours, receipt = build_migrated_setup(
            preview,
            _mappings(),
            _catalog(_ac_entry(), _humidifier_entry()),
        )

        rolled_registry, rolled_contours = rollback_migrated_setup(
            registry, contours, receipt
        )

        self.assertEqual(ClimateRegistry(), rolled_registry)
        self.assertEqual(ContourRegistry(), rolled_contours)

    def test_rollback_blocked_after_manual_changes(self) -> None:
        from custom_components.hausman_hub.application.climate_migration import (
            rollback_migrated_setup,
        )
        from custom_components.hausman_hub.domain.climate import (
            ClimateRegistry,
            ClimateRoom,
        )

        preview = build_migration_preview(_snapshot())
        registry, contours, receipt = build_migrated_setup(
            preview,
            _mappings(),
            _catalog(_ac_entry(), _humidifier_entry()),
        )
        changed = ClimateRegistry(
            rooms=(*registry.rooms, ClimateRoom(room_id="extra", name="Extra")),
            devices=registry.devices,
        )

        with self.assertRaises(ClimateMigrationViolation):
            rollback_migrated_setup(changed, contours, receipt)
