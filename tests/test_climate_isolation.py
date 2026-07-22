"""Tests for independent room and device failure containment."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from custom_components.hausman_hub.application import climate_isolation
from tests.climate_bridge_fixture import (
    import_climate_state,
)
from custom_components.hausman_hub.application.climate_isolation import (
    build_isolated_climate_policy_snapshot,
)
from custom_components.hausman_hub.application.climate_observations import (
    build_climate_observation_snapshot,
)
from custom_components.hausman_hub.application.contours import (
    build_climate_contour_setup,
)
from custom_components.hausman_hub.domain.climate_equipment import (
    ClimateEquipmentViolation,
)
from custom_components.hausman_hub.domain.climate_isolation import (
    ClimateIsolationReason,
    ClimateIsolationViolation,
    ClimateRoomIsolationStatus,
)
from custom_components.hausman_hub.domain.climate_observation import (
    ClimateDeviceAvailability,
)
from custom_components.hausman_hub.domain.climate_policy import (
    ClimateFinalDeviceAction,
)
from tests.test_contours import source_payload


NOW = 1_800_000_000_000


def _source_snapshot():
    payload = source_payload()
    return import_climate_state(
        payload,
        now_ms=payload["generatedAt"] + 1_000,  # type: ignore[operator]
    )


def _two_room_inputs():
    snapshot = _source_snapshot()
    registry, contours = build_climate_contour_setup(
        snapshot,
        room_ids=["living", "kids"],
        source_ids=[
            "synthetic-ac-source-living",
            "synthetic-humidifier-source-kids",
        ],
        name="Климат",
        mode="automatic",
        target_temperature=25.0,
        target_humidity=45,
        strategy="normal",
    )
    observation = build_climate_observation_snapshot(
        registry,
        snapshot,
        observed_at=NOW,
    )
    return contours.contour("climate"), observation


def _two_device_room_inputs():
    payload = source_payload()
    source_id = "synthetic-humidifier-source-living"
    payload["devices"].append(  # type: ignore[union-attr]
        {
            "id": source_id,
            "name": "Living humidifier",
            "roomId": "living",
            "domain": "humidifier",
            "category": "climate",
            "state": "off",
            "unavailable": False,
        }
    )
    payload["capabilities"].append(  # type: ignore[union-attr]
        {
            "deviceId": source_id,
            "commandTypes": [
                "humidifier.turn_on",
                "humidifier.turn_off",
                "humidifier.set_humidity",
            ],
        }
    )
    complete = import_climate_state(
        payload,
        now_ms=payload["generatedAt"] + 1_000,  # type: ignore[operator]
    )
    registry, contours = build_climate_contour_setup(
        complete,
        room_ids=["living"],
        source_ids=["synthetic-ac-source-living", source_id],
        name="Климат",
        mode="automatic",
        target_temperature=25.0,
        target_humidity=45,
        strategy="normal",
    )
    without_humidifier = replace(
        complete,
        devices=tuple(
            device for device in complete.devices if device.source_id != source_id
        ),
    )
    observation = build_climate_observation_snapshot(
        registry,
        without_humidifier,
        observed_at=NOW,
    )
    return contours.contour("climate"), observation


class ClimateIsolationTest(unittest.TestCase):
    def test_all_healthy_rooms_keep_independent_validated_policies(self) -> None:
        contour, observation = _two_room_inputs()

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            observation,
        )

        self.assertEqual(2, result.ready_room_count)
        self.assertEqual(2, result.available_policy_count)
        self.assertEqual((), result.failed_room_ids)
        self.assertFalse(result.commands_enabled)
        self.assertTrue(all(room.policy is not None for room in result.rooms))

    def test_missing_room_device_does_not_erase_other_room_policy(self) -> None:
        contour, observation = _two_room_inputs()
        damaged = replace(
            observation,
            devices=tuple(
                device for device in observation.devices if device.room_id != "living"
            ),
        )

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            damaged,
        )

        living = result.room("living")
        kids = result.room("kids")
        self.assertIs(living.status, ClimateRoomIsolationStatus.FAILED)  # type: ignore[union-attr]
        self.assertEqual(
            (
                ClimateIsolationReason.DEVICE_INPUT_MISSING,
                ClimateIsolationReason.NO_USABLE_DEVICES,
            ),
            living.reasons,  # type: ignore[union-attr]
        )
        self.assertIsNone(living.policy)  # type: ignore[union-attr]
        self.assertIs(kids.status, ClimateRoomIsolationStatus.READY)  # type: ignore[union-attr]
        self.assertIsNotNone(kids.policy)  # type: ignore[union-attr]
        self.assertEqual(("living",), result.failed_room_ids)

    def test_missing_room_input_does_not_erase_other_room_policy(self) -> None:
        contour, observation = _two_room_inputs()
        damaged = replace(
            observation,
            rooms=tuple(room for room in observation.rooms if room.room_id != "living"),
            devices=tuple(
                device for device in observation.devices if device.room_id != "living"
            ),
        )

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            damaged,
        )

        self.assertEqual(
            (ClimateIsolationReason.ROOM_INPUT_MISSING,),
            result.room("living").reasons,  # type: ignore[union-attr]
        )
        self.assertIsNone(result.room("living").policy)  # type: ignore[union-attr]
        self.assertIs(
            result.room("kids").status,  # type: ignore[union-attr]
            ClimateRoomIsolationStatus.READY,
        )

    def test_missing_device_keeps_healthy_device_in_the_same_room(self) -> None:
        contour, observation = _two_device_room_inputs()

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            observation,
        )

        room = result.room("living")
        self.assertIs(room.status, ClimateRoomIsolationStatus.DEGRADED)  # type: ignore[union-attr]
        self.assertEqual(
            (ClimateIsolationReason.DEVICE_MISSING,),
            room.reasons,  # type: ignore[union-attr]
        )
        self.assertEqual(
            ("living_humidifier",),
            room.failed_device_ids,  # type: ignore[union-attr]
        )
        actions = {
            device.device_id: device.action
            for device in room.policy.devices  # type: ignore[union-attr]
        }
        self.assertIn("living_air_conditioner", actions)
        self.assertIsNot(
            actions["living_air_conditioner"],
            ClimateFinalDeviceAction.UNAVAILABLE,
        )
        self.assertIs(
            actions["living_humidifier"],
            ClimateFinalDeviceAction.UNAVAILABLE,
        )

    def test_unavailable_device_keeps_healthy_device_in_the_same_room(self) -> None:
        contour, observation = _two_device_room_inputs()
        unavailable = replace(
            observation,
            devices=tuple(
                replace(device, availability=ClimateDeviceAvailability.UNAVAILABLE)
                if device.device_id == "living_humidifier"
                else device
                for device in observation.devices
            ),
        )

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            unavailable,
        )

        room = result.room("living")
        self.assertEqual(
            (ClimateIsolationReason.DEVICE_UNAVAILABLE,),
            room.reasons,  # type: ignore[union-attr]
        )
        actions = {
            device.device_id: device.action
            for device in room.policy.devices  # type: ignore[union-attr]
        }
        self.assertIsNot(
            actions["living_air_conditioner"],
            ClimateFinalDeviceAction.UNAVAILABLE,
        )
        self.assertIs(
            actions["living_humidifier"],
            ClimateFinalDeviceAction.UNAVAILABLE,
        )

    def test_absent_device_is_removed_only_from_its_room_calculation(self) -> None:
        contour, observation = _two_device_room_inputs()
        damaged = replace(
            observation,
            devices=tuple(
                device
                for device in observation.devices
                if device.device_id != "living_humidifier"
            ),
        )

        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            damaged,
        )

        room = result.room("living")
        self.assertIs(room.status, ClimateRoomIsolationStatus.DEGRADED)  # type: ignore[union-attr]
        self.assertEqual(
            (ClimateIsolationReason.DEVICE_INPUT_MISSING,),
            room.reasons,  # type: ignore[union-attr]
        )
        self.assertEqual(
            ("living_air_conditioner",),
            tuple(
                device.device_id
                for device in room.policy.selected_devices  # type: ignore[union-attr]
            ),
        )

    def test_calculation_failure_is_caught_for_one_room_only(self) -> None:
        contour, observation = _two_room_inputs()
        original = climate_isolation._build_isolated_room_policy

        def calculate(single_room_contour, source_observation):
            if single_room_contour.rooms[0].room_id == "living":
                raise ClimateEquipmentViolation("synthetic isolated failure")
            return original(single_room_contour, source_observation)

        with patch.object(
            climate_isolation,
            "_build_isolated_room_policy",
            side_effect=calculate,
        ):
            result = build_isolated_climate_policy_snapshot(
                contour,  # type: ignore[arg-type]
                observation,
            )

        self.assertEqual(
            (ClimateIsolationReason.CALCULATION_FAILED,),
            result.room("living").reasons,  # type: ignore[union-attr]
        )
        self.assertIsNone(result.room("living").policy)  # type: ignore[union-attr]
        self.assertIs(
            result.room("kids").status,  # type: ignore[union-attr]
            ClimateRoomIsolationStatus.READY,
        )

    def test_model_rejects_forged_status_and_mixed_observation(self) -> None:
        contour, observation = _two_device_room_inputs()
        result = build_isolated_climate_policy_snapshot(
            contour,  # type: ignore[arg-type]
            observation,
        )
        room = result.room("living")

        with self.assertRaises(ClimateIsolationViolation):
            replace(room, status=ClimateRoomIsolationStatus.READY)  # type: ignore[arg-type]
        with self.assertRaises(ClimateIsolationViolation):
            replace(room, reasons=(ClimateIsolationReason.CALCULATION_FAILED,))  # type: ignore[arg-type]
        with self.assertRaises(ClimateIsolationViolation):
            replace(result, observed_at=result.observed_at + 1)
        with self.assertRaises(ClimateIsolationViolation):
            replace(room, failed_device_ids=["living_humidifier"])  # type: ignore[arg-type]

        serialized = json.dumps(asdict(result), ensure_ascii=False)
        for hidden in (
            "source_id",
            "entity_id",
            "service",
            "endpoint",
            "command",
            "backend_payload",
        ):
            self.assertNotIn(hidden, serialized)


if __name__ == "__main__":
    unittest.main()
