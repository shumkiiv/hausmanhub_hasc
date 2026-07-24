"""Safe creation of an unsaved HausmanHub climate contour draft."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from tests.climate_bridge_fixture import (
    import_climate_state,
)
from custom_components.hausman_hub.application.climate_registry import (
    registry_from_payload,
    registry_to_payload,
)
from custom_components.hausman_hub.application.climate_setup import (
    ClimateSetupViolation,
    build_climate_contour_draft_setup,
    climate_device_candidates,
    climate_draft_save_receipt,
    climate_setup_options,
    current_climate_contour_setup,
    create_climate_contour_draft,
    validate_climate_contour_draft,
)
from custom_components.hausman_hub.application.contours import (
    build_climate_contour_setup,
    with_climate_schedule,
)
from tests.test_climate_setup_current import configured_setup


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = ROOT / "fixtures" / "climate_bridge" / "valid_state.json"
DRAFT_FIXTURES = ROOT / "fixtures" / "hausmanhub_climate_draft_v1"
CONTRACTS = ROOT / "custom_components" / "hausman_hub" / "contracts" / "v1"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def empty_registry() -> object:
    return registry_from_payload({"version": 2, "home": {"outdoor_temperature_entity_id": None, "presence_entity_id": None, "central_heating_entity_id": None}, "rooms": [], "devices": []})


class ClimateSetupDraftTest(unittest.TestCase):
    """A short candidate reference can build only one non-persistent draft."""

    def setUp(self) -> None:
        self.snapshot = import_climate_state(load_json(SOURCE_FIXTURE))
        self.registry = empty_registry()
        self.request = load_json(DRAFT_FIXTURES / "request.json")
        self.request_validator = Draft202012Validator(
            load_json(CONTRACTS / "climate-draft-request.schema.json")
        )
        self.draft_validator = Draft202012Validator(
            load_json(CONTRACTS / "climate-draft.schema.json")
        )
        self.options_validator = Draft202012Validator(
            load_json(CONTRACTS / "climate-setup-options.schema.json")
        )
        self.validation_validator = Draft202012Validator(
            load_json(CONTRACTS / "climate-draft-validation.schema.json")
        )
        self.save_validator = Draft202012Validator(
            load_json(CONTRACTS / "climate-draft-save.schema.json")
        )

    def test_ready_draft_builds_one_exact_setup_and_private_free_receipt(self) -> None:
        draft = load_json(DRAFT_FIXTURES / "draft.json")
        draft_before = copy.deepcopy(draft)
        registry_before = registry_to_payload(self.registry)  # type: ignore[arg-type]
        snapshot_before = copy.deepcopy(self.snapshot)

        registry, contours, validation = build_climate_contour_draft_setup(
            self.registry,  # type: ignore[arg-type]
            self.snapshot,
            draft,
        )
        receipt = climate_draft_save_receipt(draft, validation)

        self.save_validator.validate(receipt)
        self.assertEqual(load_json(DRAFT_FIXTURES / "save.json"), receipt)
        self.assertEqual(["kids", "living"], [room.room_id for room in registry.rooms])
        self.assertEqual(
            ["kids_humidifier", "living_air_conditioner"],
            [device.device_id for device in registry.devices],
        )
        contour = contours.contours[0]
        self.assertEqual("climate", contour.contour_id)
        self.assertEqual("Климат дома", contour.name)
        self.assertEqual(
            [24.0, 25.0],
            [room.day_profile.target_temperature for room in contour.rooms],
        )
        self.assertEqual(draft_before, draft)
        self.assertEqual(
            registry_before,
            registry_to_payload(self.registry),  # type: ignore[arg-type]
        )
        self.assertEqual(snapshot_before, self.snapshot)
        serialized = json.dumps(receipt, ensure_ascii=True, sort_keys=True)
        for private_value in (
            "source_id",
            "synthetic-ac-source-living",
            "synthetic-humidifier-source-kids",
        ):
            self.assertNotIn(private_value, serialized)

    def test_ready_draft_is_validated_without_mutating_inputs(self) -> None:
        draft = load_json(DRAFT_FIXTURES / "draft.json")
        draft_before = copy.deepcopy(draft)
        registry_before = registry_to_payload(self.registry)  # type: ignore[arg-type]
        snapshot_before = copy.deepcopy(self.snapshot)

        validation = validate_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            self.snapshot,
            draft,
        )

        self.validation_validator.validate(validation)
        self.assertEqual(
            load_json(DRAFT_FIXTURES / "validation.json"),
            validation,
        )
        self.assertTrue(validation["save_allowed"])
        self.assertFalse(validation["command_allowed"])
        self.assertEqual(draft_before, draft)
        self.assertEqual(
            registry_before,
            registry_to_payload(self.registry),  # type: ignore[arg-type]
        )
        self.assertEqual(snapshot_before, self.snapshot)

    def test_sensor_only_room_is_blocked_with_plain_issue(self) -> None:
        source = copy.deepcopy(load_json(SOURCE_FIXTURE))
        source["rooms"] = [  # type: ignore[index]
            room for room in source["rooms"] if room["id"] == "living"  # type: ignore[index]
        ]
        source["devices"] = [  # type: ignore[index]
            {
                "id": "private-temperature-sensor",
                "name": "Датчик температуры",
                "roomId": "living",
                "domain": "sensor",
                "category": "temperature",
                "state": "25.0",
                "unavailable": False,
            }
        ]
        source["capabilities"] = []  # type: ignore[index]
        source["authorityReadiness"]["rooms"] = [  # type: ignore[index]
            room
            for room in source["authorityReadiness"]["rooms"]  # type: ignore[index]
            if room["roomId"] == "living"
        ]
        snapshot = import_climate_state(source)
        options = climate_setup_options(
            self.registry,  # type: ignore[arg-type]
            snapshot,
        )
        draft = create_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            snapshot,
            {
                "snapshot_revision": options["snapshot_revision"],
                "name": "Климат",
                "mode": "automatic",
                "rooms": [
                    {
                        "room_id": "living",
                        "target_temperature": 25.0,
                        "target_humidity": 45,
                        "strategy": "normal",
                        "devices": [
                            {
                                "candidate_id": "candidate_0001",
                                "type": "temperature_sensor",
                            }
                        ],
                    }
                ],
            },
        )

        validation = validate_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            snapshot,
            draft,
        )

        self.validation_validator.validate(validation)
        self.assertEqual("blocked", validation["status"])
        self.assertFalse(validation["save_allowed"])
        self.assertFalse(validation["command_allowed"])
        self.assertEqual(
            [
                {
                    "code": "no_controllable_device",
                    "room_id": "living",
                    "message": (
                        "В комнате нет устройства, которое может управлять климатом."
                    ),
                }
            ],
            validation["issues"],
        )
        self.assertNotIn(
            "private-temperature-sensor",
            json.dumps(validation, ensure_ascii=True, sort_keys=True),
        )
        with self.assertRaises(ClimateSetupViolation) as blocked:
            build_climate_contour_draft_setup(
                self.registry,  # type: ignore[arg-type]
                snapshot,
                draft,
            )
        self.assertEqual("draft_blocked", blocked.exception.code)

    def test_changed_draft_or_candidate_snapshot_cannot_be_validated(self) -> None:
        changed_draft = copy.deepcopy(load_json(DRAFT_FIXTURES / "draft.json"))
        changed_draft["name"] = "Другой климат"  # type: ignore[index]
        with self.assertRaisesRegex(ClimateSetupViolation, "changed"):
            validate_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                changed_draft,
            )

        stale_revision = copy.deepcopy(load_json(DRAFT_FIXTURES / "draft.json"))
        stale_revision["snapshot_revision"] += 1  # type: ignore[index]
        with self.assertRaises(ClimateSetupViolation) as mismatch:
            validate_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                stale_revision,
            )
        self.assertEqual("snapshot_changed", mismatch.exception.code)

    def test_incomplete_device_capabilities_block_future_save(self) -> None:
        source = copy.deepcopy(load_json(SOURCE_FIXTURE))
        source["rooms"] = [  # type: ignore[index]
            room for room in source["rooms"] if room["id"] == "living"  # type: ignore[index]
        ]
        source["devices"] = [  # type: ignore[index]
            device
            for device in source["devices"]  # type: ignore[index]
            if device["roomId"] == "living"
        ]
        source["capabilities"] = [  # type: ignore[index]
            {
                "deviceId": "synthetic-ac-source-living",
                "commandTypes": ["climate.set_temperature"],
            }
        ]
        source["authorityReadiness"]["rooms"] = [  # type: ignore[index]
            room
            for room in source["authorityReadiness"]["rooms"]  # type: ignore[index]
            if room["roomId"] == "living"
        ]
        snapshot = import_climate_state(source)
        options = climate_setup_options(
            self.registry,  # type: ignore[arg-type]
            snapshot,
        )
        draft = create_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            snapshot,
            {
                "snapshot_revision": options["snapshot_revision"],
                "name": "Климат",
                "mode": "automatic",
                "rooms": [
                    {
                        "room_id": "living",
                        "target_temperature": 25.0,
                        "target_humidity": 45,
                        "strategy": "normal",
                        "devices": [
                            {
                                "candidate_id": "candidate_0001",
                                "type": "air_conditioner",
                            }
                        ],
                    }
                ],
            },
        )

        validation = validate_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            snapshot,
            draft,
        )

        self.validation_validator.validate(validation)
        self.assertEqual("blocked", validation["status"])
        self.assertTrue(validation["checks"]["rooms_have_controllable_devices"])
        self.assertFalse(
            validation["checks"]["device_capabilities_supported"]
        )
        self.assertEqual("unsupported_device_set", validation["issues"][0]["code"])

    def test_validation_schema_rejects_blocked_result_with_passing_checks(self) -> None:
        invalid = copy.deepcopy(load_json(DRAFT_FIXTURES / "validation.json"))
        invalid["status"] = "blocked"  # type: ignore[index]
        invalid["save_allowed"] = False  # type: ignore[index]
        invalid["issues"] = [  # type: ignore[index]
            {
                "code": "no_controllable_device",
                "room_id": "living",
                "message": (
                    "В комнате нет устройства, которое может управлять климатом."
                ),
            }
        ]

        with self.assertRaises(Exception):
            self.validation_validator.validate(invalid)

    def test_setup_options_are_exact_understandable_and_private_id_free(self) -> None:
        options = climate_setup_options(
            self.registry,  # type: ignore[arg-type]
            self.snapshot,
        )

        self.options_validator.validate(options)
        self.assertEqual(load_json(DRAFT_FIXTURES / "options.json"), options)
        self.assertTrue(options["draft_creation_allowed"])
        serialized = json.dumps(options, ensure_ascii=True, sort_keys=True)
        for private_value in (
            "source_id",
            "entity_id",
            "synthetic-ac-source-living",
            "synthetic-humidifier-source-kids",
        ):
            self.assertNotIn(private_value, serialized)

        stale_payload = copy.deepcopy(load_json(SOURCE_FIXTURE))
        stale_payload["runtimeHealth"]["status"] = "stale"  # type: ignore[index]
        stale = climate_setup_options(
            self.registry,  # type: ignore[arg-type]
            import_climate_state(stale_payload),
        )
        self.options_validator.validate(stale)
        self.assertFalse(stale["draft_creation_allowed"])
        self.assertFalse(any(device["can_add"] for device in stale["devices"]))

    def test_valid_request_creates_exact_sorted_private_id_free_draft(self) -> None:
        request_before = copy.deepcopy(self.request)
        registry_before = registry_to_payload(self.registry)  # type: ignore[arg-type]
        snapshot_before = copy.deepcopy(self.snapshot)

        draft = create_climate_contour_draft(
            self.registry,  # type: ignore[arg-type]
            self.snapshot,
            self.request,
        )

        self.request_validator.validate(self.request)
        self.draft_validator.validate(draft)
        self.assertEqual(load_json(DRAFT_FIXTURES / "draft.json"), draft)
        self.assertFalse(draft["save_allowed"])
        self.assertTrue(draft["validation_required"])
        self.assertEqual(request_before, self.request)
        self.assertEqual(
            registry_before,
            registry_to_payload(self.registry),  # type: ignore[arg-type]
        )
        self.assertEqual(snapshot_before, self.snapshot)
        serialized = json.dumps(draft, ensure_ascii=True, sort_keys=True)
        for private_value in (
            "source_id",
            "entity_id",
            "synthetic-ac-source-living",
            "synthetic-humidifier-source-kids",
        ):
            self.assertNotIn(private_value, serialized)

    def test_changed_or_stale_candidate_snapshot_is_rejected_as_conflict(self) -> None:
        changed = copy.deepcopy(self.request)
        changed["snapshot_revision"] += 1  # type: ignore[index]
        with self.assertRaises(ClimateSetupViolation) as mismatch:
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                changed,
            )
        self.assertEqual("snapshot_changed", mismatch.exception.code)

        stale_payload = copy.deepcopy(load_json(SOURCE_FIXTURE))
        stale_payload["runtimeHealth"]["status"] = "stale"  # type: ignore[index]
        with self.assertRaises(ClimateSetupViolation) as stale:
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                import_climate_state(stale_payload),
                self.request,
            )
        self.assertEqual("data_stale", stale.exception.code)

    def test_candidate_cannot_be_reused_or_moved_to_another_room(self) -> None:
        repeated = copy.deepcopy(self.request)
        repeated["rooms"][1]["devices"] = [  # type: ignore[index]
            {"candidate_id": "candidate_0002", "type": "air_conditioner"}
        ]
        with self.assertRaisesRegex(ClimateSetupViolation, "repeated"):
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                repeated,
            )

        moved = copy.deepcopy(self.request)
        moved["rooms"] = [  # type: ignore[index]
            {
                "room_id": "living",
                "target_temperature": 25.0,
                "target_humidity": 45,
                "strategy": "normal",
                "devices": [
                    {"candidate_id": "candidate_0001", "type": "humidifier"}
                ],
            }
        ]
        with self.assertRaisesRegex(ClimateSetupViolation, "room differs"):
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                moved,
            )

    def test_only_detected_device_type_and_valid_comfort_values_are_accepted(self) -> None:
        wrong_type = copy.deepcopy(self.request)
        wrong_type["rooms"][0]["devices"][0]["type"] = "humidifier"  # type: ignore[index]
        with self.assertRaisesRegex(ClimateSetupViolation, "type is invalid"):
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                wrong_type,
            )

        for field, invalid in (
            ("target_temperature", 25.2),
            ("target_humidity", 47),
            ("strategy", "turbo"),
        ):
            with self.subTest(field=field):
                request = copy.deepcopy(self.request)
                request["rooms"][0][field] = invalid  # type: ignore[index]
                with self.assertRaises(ClimateSetupViolation):
                    create_climate_contour_draft(
                        self.registry,  # type: ignore[arg-type]
                        self.snapshot,
                        request,
                    )

    def test_configured_candidate_is_accepted_only_unchanged_in_its_room(self) -> None:
        configured_registry = registry_from_payload(
            load_json(ROOT / "fixtures" / "hausmanhub_climate_v1" / "registry.json")
        )
        configured_request = copy.deepcopy(self.request)
        configured_request["snapshot_revision"] = climate_device_candidates(
            configured_registry,
            self.snapshot,
        )["snapshot_revision"]  # type: ignore[index]
        draft = create_climate_contour_draft(
            configured_registry,
            self.snapshot,
            configured_request,
        )
        self.draft_validator.validate(draft)

        retyped = copy.deepcopy(configured_request)
        retyped["rooms"][0]["devices"][0]["type"] = "floor_heating"  # type: ignore[index]
        with self.assertRaisesRegex(ClimateSetupViolation, "unavailable"):
            create_climate_contour_draft(
                configured_registry,
                self.snapshot,
                retyped,
            )

        moved = copy.deepcopy(configured_request)
        moved["rooms"][0]["devices"] = [  # type: ignore[index]
            {"candidate_id": "candidate_0001", "type": "humidifier"}
        ]
        with self.assertRaisesRegex(ClimateSetupViolation, "unavailable"):
            create_climate_contour_draft(
                configured_registry,
                self.snapshot,
                moved,
            )

        extra = copy.deepcopy(self.request)
        extra["confirm"] = True  # type: ignore[index]
        with self.assertRaisesRegex(ClimateSetupViolation, "fields"):
            create_climate_contour_draft(
                self.registry,  # type: ignore[arg-type]
                self.snapshot,
                extra,
            )

    def test_edit_preserves_profiles_schedule_overrides_bindings_and_ids(self) -> None:
        registry, contours, snapshot = configured_setup()
        registry_payload = registry_to_payload(registry)  # type: ignore[arg-type]
        registry_payload["home"]["outdoor_temperature_entity_id"] = (  # type: ignore[index]
            "sensor.outdoor"
        )
        for room_payload in registry_payload["rooms"]:  # type: ignore[union-attr]
            if room_payload["id"] == "living":
                room_payload["window_entity_id"] = "binary_sensor.living_window"
                room_payload["presence_entity_ids"] = [
                    "binary_sensor.living_motion",
                    "binary_sensor.living_occupancy",
                ]
        registry = registry_from_payload(registry_payload)
        current = current_climate_contour_setup(
            registry,
            contours,  # type: ignore[arg-type]
            snapshot,  # type: ignore[arg-type]
        )
        request_rooms = []
        for room in current["rooms"]:  # type: ignore[union-attr]
            active_profile = room["profiles"]["active_profile"]
            active = room["profiles"][active_profile]
            request_rooms.append(
                {
                    "room_id": room["id"],
                    "target_temperature": (
                        26.0 if room["id"] == "living" else active["target_temperature"]
                    ),
                    "target_humidity": active["target_humidity"],
                    "strategy": active["strategy"],
                    "devices": [
                        {
                            "candidate_id": device["candidate_id"],
                            "type": device["type"],
                        }
                        for device in room["devices"]
                    ],
                }
            )
        request = {
            "snapshot_revision": current["snapshot_revision"],
            "setup_revision": current["setup_revision"],
            "name": current["name"],
            "mode": current["mode"],
            "rooms": request_rooms,
        }
        self.request_validator.validate(request)
        missing_revision = copy.deepcopy(request)
        missing_revision.pop("setup_revision")
        with self.assertRaises(ClimateSetupViolation) as missing:
            create_climate_contour_draft(
                registry,
                snapshot,  # type: ignore[arg-type]
                missing_revision,
                contours=contours,  # type: ignore[arg-type]
            )
        self.assertEqual("setup_changed", missing.exception.code)
        draft = create_climate_contour_draft(
            registry,
            snapshot,  # type: ignore[arg-type]
            request,
            contours=contours,  # type: ignore[arg-type]
        )

        updated_registry, updated_contours, validation = (
            build_climate_contour_draft_setup(
                registry,
                snapshot,  # type: ignore[arg-type]
                draft,
                contours=contours,  # type: ignore[arg-type]
            )
        )

        self.assertEqual("ready", validation["status"])
        updated = updated_contours.contour("climate")
        self.assertIsNotNone(updated)
        assert updated is not None
        living = next(room for room in updated.rooms if room.room_id == "living")
        kids = next(room for room in updated.rooms if room.room_id == "kids")
        self.assertEqual(26.0, living.day_profile.target_temperature)
        self.assertEqual(22.0, living.night_profile.target_temperature)
        self.assertEqual(21.0, kids.night_profile.target_temperature)
        self.assertTrue(updated.schedule.enabled)
        self.assertEqual("07:00", updated.schedule.day_start)
        self.assertEqual("day", updated.schedule.last_applied_profile.value)  # type: ignore[union-attr]
        self.assertEqual(23.5, living.temporary_override.target_temperature)  # type: ignore[union-attr]
        self.assertEqual(
            [device.device_id for device in registry.devices],  # type: ignore[union-attr]
            [device.device_id for device in updated_registry.devices],
        )
        self.assertEqual(
            "sensor.outdoor",
            updated_registry.home.outdoor_temperature_entity_id,
        )
        self.assertEqual(
            "binary_sensor.living_window",
            updated_registry.room("living").window_entity_id,  # type: ignore[union-attr]
        )
        self.assertEqual(
            (
                "binary_sensor.living_motion",
                "binary_sensor.living_occupancy",
            ),
            updated_registry.room("living").presence_entity_ids,  # type: ignore[union-attr]
        )

        stale_request = copy.deepcopy(request)
        stale_request["setup_revision"] += 1
        with self.assertRaises(ClimateSetupViolation) as stale:
            create_climate_contour_draft(
                registry,
                snapshot,  # type: ignore[arg-type]
                stale_request,
                contours=contours,  # type: ignore[arg-type]
            )
        self.assertEqual("setup_changed", stale.exception.code)

        changed_contours = with_climate_schedule(
            contours,  # type: ignore[arg-type]
            enabled=True,
            day_start="08:00",
            night_start="23:00",
        )
        with self.assertRaises(ClimateSetupViolation) as changed:
            validate_climate_contour_draft(
                registry,
                snapshot,  # type: ignore[arg-type]
                draft,
                contours=changed_contours,
            )
        self.assertEqual("setup_changed", changed.exception.code)

    def test_adding_an_earlier_sensor_keeps_existing_public_device_id(self) -> None:
        initial_source = copy.deepcopy(load_json(SOURCE_FIXTURE))
        initial_source["devices"].append(  # type: ignore[union-attr]
            {
                "id": "sensor-zulu",
                "name": "Zulu temperature",
                "roomId": "living",
                "domain": "sensor",
                "category": "temperature",
                "state": "22.0",
                "unavailable": False,
            }
        )
        initial_snapshot = import_climate_state(initial_source)
        registry, contours = build_climate_contour_setup(
            initial_snapshot,
            room_ids=["living"],
            source_ids=["synthetic-ac-source-living", "sensor-zulu"],
            name="Климат",
            mode="automatic",
            target_temperature=22.0,
            target_humidity=45,
            strategy="normal",
        )
        zulu_before = next(
            device for device in registry.devices if device.source_id == "sensor-zulu"
        )

        updated_source = copy.deepcopy(initial_source)
        updated_source["devices"].append(  # type: ignore[union-attr]
            {
                "id": "sensor-alpha",
                "name": "Alpha temperature",
                "roomId": "living",
                "domain": "sensor",
                "category": "temperature",
                "state": "23.0",
                "unavailable": False,
            }
        )
        updated_snapshot = import_climate_state(updated_source)
        options = climate_setup_options(registry, updated_snapshot)
        current = current_climate_contour_setup(
            registry,
            contours,
            updated_snapshot,
        )
        candidate_by_name = {
            device["name"]: device["candidate_id"]
            for device in options["devices"]  # type: ignore[union-attr]
        }
        current_room = current["rooms"][0]  # type: ignore[index]
        devices = [
            {
                "candidate_id": device["candidate_id"],
                "type": device["type"],
            }
            for device in current_room["devices"]
        ]
        devices.append(
            {
                "candidate_id": candidate_by_name["Alpha temperature"],
                "type": "temperature_sensor",
            }
        )
        draft = create_climate_contour_draft(
            registry,
            updated_snapshot,
            {
                "snapshot_revision": options["snapshot_revision"],
                "setup_revision": current["setup_revision"],
                "name": "Климат",
                "mode": "automatic",
                "rooms": [
                    {
                        "room_id": "living",
                        "target_temperature": 22.0,
                        "target_humidity": 45,
                        "strategy": "normal",
                        "devices": devices,
                    }
                ],
            },
            contours=contours,
        )

        updated_registry, updated_contours, _ = build_climate_contour_draft_setup(
            registry,
            updated_snapshot,
            draft,
            contours=contours,
        )

        zulu_after = next(
            device
            for device in updated_registry.devices
            if device.source_id == "sensor-zulu"
        )
        alpha = next(
            device
            for device in updated_registry.devices
            if device.source_id == "sensor-alpha"
        )
        self.assertEqual(zulu_before.device_id, zulu_after.device_id)
        self.assertNotEqual(zulu_after.device_id, alpha.device_id)
        saved = updated_contours.contour("climate")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(
            {device.device_id for device in updated_registry.devices},
            set(saved.rooms[0].device_ids),
        )


if __name__ == "__main__":
    unittest.main()
