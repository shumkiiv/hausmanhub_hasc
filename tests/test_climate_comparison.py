"""Tests for the command-free decision comparison with the working module."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest

from custom_components.hausman_hub.application.climate_comparison import (
    build_climate_comparison_snapshot,
)
from custom_components.hausman_hub.application.climate_import import (
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
from custom_components.hausman_hub.domain.climate_comparison import (
    ClimateComparisonReason,
    ClimateComparisonSnapshot,
    ClimateComparisonStatus,
    ClimateComparisonViolation,
    ClimateDeviceComparison,
    ClimateRoomComparison,
)
from custom_components.hausman_hub.domain.climate_isolation import (
    ClimateRoomIsolationStatus,
)
from custom_components.hausman_hub.domain.climate_observation import (
    ClimateDeviceActivity,
    ClimateObservationDeviceKind,
    ClimateRoomMode,
    ClimateWindowState,
)
from custom_components.hausman_hub.domain.climate_policy import (
    ClimateFinalDeviceAction,
    ClimatePolicyAction,
    ClimateRoomPolicy,
)
from custom_components.hausman_hub.domain.contours import ContourMode
from tests.test_contours import source_payload


NOW = 1_800_000_000_000
LIVING = ["living"]
LIVING_AC = ["synthetic-ac-source-living"]


def _setup(payload):
    snapshot = import_climate_state(
        payload,
        now_ms=payload["generatedAt"] + 1_000,  # type: ignore[operator]
    )
    return build_climate_contour_setup(
        snapshot,
        room_ids=LIVING,
        source_ids=LIVING_AC,
        name="Климат",
        mode="automatic",
        target_temperature=25.0,
        target_humidity=45,
        strategy="normal",
    )


def _observation(registry, payload, *, observed_at: int = NOW):
    snapshot = import_climate_state(
        payload,
        now_ms=payload["generatedAt"] + 1_000,  # type: ignore[operator]
    )
    return build_climate_observation_snapshot(
        registry,
        snapshot,
        observed_at=observed_at,
    )


def _comparison(payload, *, mutate_observation=None, observed_at: int = NOW):
    registry, contours = _setup(source_payload())
    observation = _observation(registry, payload, observed_at=observed_at)
    if mutate_observation is not None:
        observation = mutate_observation(observation)
    isolation = build_isolated_climate_policy_snapshot(
        contours.contour("climate"),
        observation,
    )
    return build_climate_comparison_snapshot(isolation, observation), isolation


def _close_windows(observation):
    return replace(
        observation,
        rooms=tuple(
            replace(room, window=ClimateWindowState.CLOSED)
            for room in observation.rooms
        ),
    )


class ClimateComparisonBuilderTest(unittest.TestCase):
    def test_aligned_room_and_device_report_no_reasons(self) -> None:
        payload = source_payload()
        payload["devices"][0]["state"] = "off"  # type: ignore[index]

        comparison, isolation = _comparison(payload)

        self.assertFalse(comparison.commands_enabled)
        self.assertEqual(1, comparison.aligned_room_count)
        self.assertEqual((), comparison.diverged_room_ids)
        self.assertEqual((), comparison.not_comparable_room_ids)
        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.ALIGNED)
        self.assertEqual((), room.reasons)
        self.assertIs(room.planned_policy, ClimateRoomPolicy.SAFETY_LOCKOUT)
        self.assertIs(room.planned_action, ClimatePolicyAction.SAFE_OFF)
        self.assertIs(room.observed_mode, ClimateRoomMode.AUTO)
        (device,) = room.devices
        self.assertIs(device.status, ClimateComparisonStatus.ALIGNED)
        self.assertIs(device.planned_action, ClimateFinalDeviceAction.OFF)
        self.assertIs(device.observed_activity, ClimateDeviceActivity.STOPPED)
        self.assertIs(
            isolation.room("living").status,  # type: ignore[union-attr]
            ClimateRoomIsolationStatus.READY,
        )

    def test_running_module_diverges_from_the_safe_stop_plan(self) -> None:
        comparison, _ = _comparison(source_payload())

        self.assertEqual(("living",), comparison.diverged_room_ids)
        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.DIVERGED)
        self.assertEqual(
            (ClimateComparisonReason.DEVICE_ACTIVITY_MISMATCH,),
            room.reasons,
        )
        (device,) = room.devices
        self.assertIs(device.status, ClimateComparisonStatus.DIVERGED)
        self.assertIs(device.planned_action, ClimateFinalDeviceAction.SAFE_OFF)
        self.assertIs(device.observed_activity, ClimateDeviceActivity.COOLING)

    def test_unobserved_module_settings_limit_the_comparison(self) -> None:
        comparison, _ = _comparison(
            source_payload(),
            mutate_observation=_close_windows,
        )

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.DEVICE_SETTING_UNOBSERVED,),
            room.reasons,
        )
        (device,) = room.devices
        self.assertIs(device.planned_action, ClimateFinalDeviceAction.COOL)
        self.assertIs(device.observed_activity, ClimateDeviceActivity.COOLING)

    def test_mismatched_module_settings_diverge(self) -> None:
        def mutate(observation):
            observation = _close_windows(observation)
            return replace(
                observation,
                devices=tuple(
                    replace(device, current_target_temperature=24.0)
                    for device in observation.devices
                ),
            )

        comparison, _ = _comparison(source_payload(), mutate_observation=mutate)

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.DIVERGED)
        self.assertEqual(
            (
                ClimateComparisonReason.DEVICE_SETTING_UNOBSERVED,
                ClimateComparisonReason.DEVICE_SETTING_MISMATCH,
            ),
            room.reasons,
        )

    def test_unavailable_device_limits_only_its_comparison(self) -> None:
        payload = source_payload()
        payload["devices"][0]["unavailable"] = True  # type: ignore[index]

        comparison, isolation = _comparison(payload)

        self.assertIs(
            isolation.room("living").status,  # type: ignore[union-attr]
            ClimateRoomIsolationStatus.DEGRADED,
        )
        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.DEVICE_UNAVAILABLE,),
            room.reasons,
        )

    def test_stale_observation_short_circuits_every_room(self) -> None:
        registry, contours = _setup(source_payload())
        stale_payload = source_payload()
        snapshot = import_climate_state(
            stale_payload,
            now_ms=stale_payload["generatedAt"] + 10 * 60 * 1000,  # type: ignore[operator]
        )
        observation = build_climate_observation_snapshot(
            registry,
            snapshot,
            observed_at=NOW,
        )
        isolation = build_isolated_climate_policy_snapshot(
            contours.contour("climate"),
            observation,
        )

        comparison = build_climate_comparison_snapshot(isolation, observation)

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.OBSERVATION_STALE,),
            room.reasons,
        )
        self.assertEqual((), room.devices)
        self.assertIsNotNone(room.planned_policy)

    def test_manual_room_is_reported_as_observe_only(self) -> None:
        def mutate(observation):
            observation = _close_windows(observation)
            return replace(
                observation,
                rooms=tuple(
                    replace(room, mode=ClimateRoomMode.MANUAL)
                    for room in observation.rooms
                ),
            )

        comparison, _ = _comparison(source_payload(), mutate_observation=mutate)

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.MANUAL_OBSERVE,),
            room.reasons,
        )
        self.assertIs(room.planned_action, ClimatePolicyAction.OBSERVE)
        self.assertEqual((), room.devices)

    def test_dropped_module_device_limits_the_comparison(self) -> None:
        registry, contours = _setup(source_payload())
        payload = source_payload()
        payload["devices"] = []
        observation = _observation(registry, payload)
        isolation = build_isolated_climate_policy_snapshot(
            contours.contour("climate"),
            observation,
        )

        comparison = build_climate_comparison_snapshot(isolation, observation)

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.DEVICE_UNAVAILABLE,),
            room.reasons,
        )

    def test_failed_room_reports_missing_policy(self) -> None:
        registry, contours = _setup(source_payload())
        observation = replace(
            _observation(registry, source_payload()),
            devices=(),
        )
        isolation = build_isolated_climate_policy_snapshot(
            contours.contour("climate"),
            observation,
        )
        self.assertIs(
            isolation.room("living").status,  # type: ignore[union-attr]
            ClimateRoomIsolationStatus.FAILED,
        )

        comparison = build_climate_comparison_snapshot(isolation, observation)

        room = comparison.room("living")  # type: ignore[union-attr]
        self.assertIs(room.status, ClimateComparisonStatus.NOT_COMPARABLE)
        self.assertEqual(
            (ClimateComparisonReason.ROOM_POLICY_MISSING,),
            room.reasons,
        )
        self.assertIsNone(room.planned_policy)
        self.assertIsNone(room.planned_action)
        self.assertEqual((), room.devices)

    def test_comparison_requires_one_shared_observation_time(self) -> None:
        registry, contours = _setup(source_payload())
        observation = _observation(registry, source_payload(), observed_at=NOW)
        isolation = build_isolated_climate_policy_snapshot(
            contours.contour("climate"),
            observation,
        )
        other = _observation(registry, source_payload(), observed_at=NOW + 1_000)

        with self.assertRaises(ClimateComparisonViolation):
            build_climate_comparison_snapshot(isolation, other)


class ClimateComparisonModelTest(unittest.TestCase):
    def _device(self, **overrides) -> ClimateDeviceComparison:
        values = {
            "device_id": "living_air_conditioner",
            "room_id": "living",
            "kind": ClimateObservationDeviceKind.AIR_CONDITIONER,
            "status": ClimateComparisonStatus.ALIGNED,
            "reasons": (),
            "planned_action": ClimateFinalDeviceAction.SAFE_OFF,
            "observed_activity": ClimateDeviceActivity.STOPPED,
        }
        return ClimateDeviceComparison(**(values | overrides))  # type: ignore[arg-type]

    def _room(self, **overrides) -> ClimateRoomComparison:
        values = {
            "room_id": "living",
            "status": ClimateComparisonStatus.ALIGNED,
            "reasons": (),
            "planned_policy": ClimateRoomPolicy.SAFETY_LOCKOUT,
            "planned_action": ClimatePolicyAction.SAFE_OFF,
            "observed_mode": ClimateRoomMode.AUTO,
            "devices": (),
        }
        return ClimateRoomComparison(**(values | overrides))  # type: ignore[arg-type]

    def test_result_rejects_contradictory_status_and_reasons(self) -> None:
        with self.assertRaises(ClimateComparisonViolation):
            self._device(
                status=ClimateComparisonStatus.ALIGNED,
                reasons=(ClimateComparisonReason.DEVICE_UNAVAILABLE,),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._device(
                status=ClimateComparisonStatus.DIVERGED,
                reasons=(ClimateComparisonReason.DEVICE_UNAVAILABLE,),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._device(status=ClimateComparisonStatus.NOT_COMPARABLE, reasons=())
        with self.assertRaises(ClimateComparisonViolation):
            self._device(
                status=ClimateComparisonStatus.NOT_COMPARABLE,
                reasons=(
                    ClimateComparisonReason.DEVICE_SETTING_UNOBSERVED,
                    ClimateComparisonReason.DEVICE_UNAVAILABLE,
                ),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._device(
                status=ClimateComparisonStatus.NOT_COMPARABLE,
                reasons=(
                    ClimateComparisonReason.DEVICE_UNAVAILABLE,
                    ClimateComparisonReason.DEVICE_UNAVAILABLE,
                ),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._device(reasons=[ClimateComparisonReason.DEVICE_UNAVAILABLE])  # type: ignore[arg-type]

    def test_room_rejects_forged_shape(self) -> None:
        with self.assertRaises(ClimateComparisonViolation):
            self._room(planned_action=None)
        with self.assertRaises(ClimateComparisonViolation):
            self._room(
                status=ClimateComparisonStatus.DIVERGED,
                reasons=(ClimateComparisonReason.DEVICE_ACTIVITY_MISMATCH,),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._room(
                devices=(
                    self._device(status=ClimateComparisonStatus.DIVERGED),
                ),
            )
        with self.assertRaises(ClimateComparisonViolation):
            self._room(devices=(self._device(room_id="kids"),))

    def test_snapshot_rejects_mutable_mixed_or_forged_rooms(self) -> None:
        room = self._room()
        with self.assertRaises(ClimateComparisonViolation):
            ClimateComparisonSnapshot(
                contour_id="climate",
                contour_mode=ContourMode.AUTOMATIC,
                observed_at=NOW,
                rooms=(),
            )
        with self.assertRaises(ClimateComparisonViolation):
            ClimateComparisonSnapshot(
                contour_id="climate",
                contour_mode=ContourMode.AUTOMATIC,
                observed_at=NOW,
                rooms=(room, room),
            )
        with self.assertRaises(ClimateComparisonViolation):
            ClimateComparisonSnapshot(
                contour_id="climate",
                contour_mode=ContourMode.AUTOMATIC,
                observed_at=NOW,
                rooms=[room],  # type: ignore[arg-type]
            )
        with self.assertRaises(ClimateComparisonViolation):
            ClimateComparisonSnapshot(
                contour_id="climate",
                contour_mode=ContourMode.AUTOMATIC,
                observed_at=NOW,
                rooms=(room,),
                version=True,  # type: ignore[arg-type]
            )

    def test_snapshot_stays_command_free_and_private_free(self) -> None:
        comparison, _ = _comparison(source_payload())
        serialized = json.dumps(asdict(comparison), ensure_ascii=False)

        self.assertFalse(comparison.commands_enabled)
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
