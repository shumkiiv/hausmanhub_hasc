"""Golden and parity tests for the native projection builders (36e1).

The native builders must reproduce the legacy bridge-derived payloads for the
same physical situation wherever the semantics overlap, and must fail closed
(never permissive) when native evidence is missing, stale, or unavailable.

Number note: the legacy importer preserves JSON ints (``44``) while native
Home Assistant states always parse to floats (``44.0``). Both serialize as
equal JSON numbers for Android, but the internal ``state_revision`` hash and
raw dict comparison see a type difference, so parity comparison normalizes
integral floats to ints and checks ``state_revision`` separately.
"""

from __future__ import annotations

import unittest

from custom_components.hausman_hub.application.android_climate import (
    admin_climate_import_snapshot,
    android_climate_snapshot,
)
from custom_components.hausman_hub.application.climate_ha_observations import (
    build_native_ha_climate_observation,
)
from custom_components.hausman_hub.application.climate_import import (
    import_climate_state,
)
from custom_components.hausman_hub.application.climate_native_projections import (
    native_admin_climate_import_snapshot,
    native_android_climate_snapshot,
    native_climate_readiness,
    native_contour_apply_preview,
    native_contour_snapshot,
    native_device_command_types,
)
from custom_components.hausman_hub.application.contour_apply import (
    ContourApplyViolation,
    contour_fingerprint,
)
from custom_components.hausman_hub.application.contours import (
    build_climate_contour_setup,
    contour_snapshot,
)
from custom_components.hausman_hub.application.climate_runtime import (
    _legacy_contour_apply_preview,
)
from custom_components.hausman_hub.domain.climate_bridge import ClimateBridgeMode
from custom_components.hausman_hub.domain.climate_observation import (
    ClimateDataStatus,
)
from custom_components.hausman_hub.domain.climate_protection import (
    empty_climate_protection_memory,
)
from tests.test_climate_import import source_payload
from tests.test_climate_runtime import (
    MemoryBridge,
    SnapshotStateView,
    with_native_observation_bindings,
)

NOW_MS = 1784280005000
GENERATED_AT = 1784280000000

_SENSOR_DEVICES = (
    {
        "id": "synthetic-living_temperature_observation",
        "name": "Living room temperature observation",
        "roomId": "living",
        "domain": "sensor",
        "category": "temperature",
        "state": "25.8",
        "unavailable": False,
    },
    {
        "id": "synthetic-living_humidity_observation",
        "name": "Living room humidity observation",
        "roomId": "living",
        "domain": "sensor",
        "category": "humidity",
        "state": "44.0",
        "unavailable": False,
    },
)


def _extended_source_payload() -> dict[str, object]:
    """Return the shared fixture plus the native observation sensor devices."""

    payload = source_payload()
    payload["devices"].extend(_SENSOR_DEVICES)  # type: ignore[union-attr]
    return payload


def _normalize(value: object) -> object:
    """Convert integral floats to ints recursively for parity comparison."""

    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _setup():
    """Return (registry, contours, legacy snapshot) for one managed room."""

    legacy = import_climate_state(_extended_source_payload(), now_ms=NOW_MS)
    registry, contours = build_climate_contour_setup(
        legacy,
        room_ids=["living"],
        source_ids=["synthetic-ac-source-living"],
        name="Климат",
        mode="automatic",
        room_parameters={
            "living": {
                "target_temperature": 25.0,
                "target_humidity": 45,
                "strategy": "normal",
            }
        },
    )
    return registry, contours, legacy


def _native_observation(registry, contours):
    """Build the native observation for the same synthetic physical state."""

    bound = with_native_observation_bindings(registry)
    bridge = MemoryBridge()
    bridge.snapshot = import_climate_state(
        _extended_source_payload(), now_ms=NOW_MS
    )
    states = SnapshotStateView(bound, bridge)
    observation = build_native_ha_climate_observation(
        bound,
        contours.contour("climate"),
        states,
        observed_at=GENERATED_AT,
        protection=empty_climate_protection_memory(updated_at=GENERATED_AT),
        local_time=(12, 0),
    )
    return bound, observation


def _with_data_status(observation, status: ClimateDataStatus):
    return type(observation)(
        observed_at=observation.observed_at,
        source_generated_at=observation.source_generated_at,
        data_status=status,
        home=observation.home,
        control=observation.control,
        rooms=observation.rooms,
        devices=observation.devices,
    )


class NativeAndroidParityTest(unittest.TestCase):
    """The tablet contract must match the legacy payload for the same facts."""

    def test_native_android_snapshot_matches_legacy_payload(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)

        expected = android_climate_snapshot(
            bound,
            legacy,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )
        result = native_android_climate_snapshot(
            bound,
            observation,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )

        self.assertEqual(GENERATED_AT, result["generated_at"])
        self.assertIsInstance(result["state_revision"], int)
        # Locked semantic difference: legacy reconciliation reports the
        # bridge-only humidifier as an unregistered source (matches False);
        # native reconciliation covers only configured devices (matches True,
        # zero unregistered). Everything else must be byte-identical.
        legacy_reconciliation = expected.pop("reconciliation")
        native_reconciliation = result.pop("reconciliation")
        self.assertEqual(
            {
                "matches": False,
                "matched_device_ids": ["living_air_conditioner",
                                       "living_humidity_observation",
                                       "living_temperature_observation"],
                "missing_device_ids": [],
                "room_mismatch_device_ids": [],
                "unregistered_device_count": 1,
            },
            legacy_reconciliation,
        )
        self.assertEqual(
            {
                "matches": True,
                "matched_device_ids": ["living_air_conditioner",
                                       "living_humidity_observation",
                                       "living_temperature_observation"],
                "missing_device_ids": [],
                "room_mismatch_device_ids": [],
                "unregistered_device_count": 0,
            },
            native_reconciliation,
        )
        expected.pop("state_revision")
        result.pop("state_revision")
        self.assertEqual(
            _normalize(expected),
            _normalize(result),
        )


class NativeContourParityTest(unittest.TestCase):
    """The public contour projection must match the legacy payload."""

    def test_native_contour_snapshot_matches_legacy_payload(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)

        expected = contour_snapshot(
            contours,
            bound,
            legacy,
            settings_apply_enabled=True,
        )
        result = native_contour_snapshot(
            contours,
            bound,
            observation,
            settings_apply_enabled=True,
        )

        self.assertEqual(_normalize(expected), _normalize(result))


class NativeAdminParityTest(unittest.TestCase):
    """The administrator payload must match registry-driven legacy content."""

    def test_native_admin_snapshot_matches_legacy_payload(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)

        expected = admin_climate_import_snapshot(bound, legacy)
        result = native_admin_climate_import_snapshot(bound, observation)

        self.assertEqual(expected["generated_at"], result["generated_at"])
        self.assertEqual(expected["fresh"], result["fresh"])
        # The native payload is scoped to configured rooms: the bridge-only
        # "kids" room honestly disappears instead of being echoed.
        self.assertEqual(
            [{"id": "living", "name": "Living room", "authority_eligible": True}],
            _normalize(result["rooms"]),
        )
        self.assertEqual(
            {
                "matches": False,
                "matched_device_ids": ["living_air_conditioner",
                                       "living_humidity_observation",
                                       "living_temperature_observation"],
                "missing_device_ids": [],
                "room_mismatch_device_ids": [],
                "unregistered_source_ids": ["synthetic-humidifier-source-kids"],
            },
            expected["reconciliation"],
        )
        self.assertEqual(
            {
                "matches": True,
                "matched_device_ids": ["living_air_conditioner",
                                       "living_humidity_observation",
                                       "living_temperature_observation"],
                "missing_device_ids": [],
                "room_mismatch_device_ids": [],
                "unregistered_source_ids": [],
            },
            result["reconciliation"],
        )
        legacy_candidates = {
            item["source_id"]: item for item in expected["candidates"]
        }
        native_candidates = {
            item["source_id"]: item for item in result["candidates"]
        }
        # Native candidates are the configured devices only; the legacy
        # payload additionally lists the unregistered bridge humidifier.
        self.assertEqual(
            set(native_candidates) | {"synthetic-humidifier-source-kids"},
            set(legacy_candidates),
        )
        for source_id, legacy_candidate in legacy_candidates.items():
            if source_id == "synthetic-humidifier-source-kids":
                continue
            native_candidate = native_candidates[source_id]
            self.assertEqual(legacy_candidate["name"], native_candidate["name"])
            self.assertEqual(
                legacy_candidate["room_id"], native_candidate["room_id"]
            )
            self.assertEqual(
                legacy_candidate["available"], native_candidate["available"]
            )
            self.assertEqual(
                set(legacy_candidate["command_types"]),
                set(native_candidate["command_types"]),
            )
            self.assertEqual(
                legacy_candidate["suggested_kinds"],
                native_candidate["suggested_kinds"],
            )


class NativeReadinessTest(unittest.TestCase):
    """Readiness must mirror the legacy reasons and fail closed."""

    def test_ready_payload_matches_legacy_semantics(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)

        result = native_climate_readiness(
            bound,
            observation,
            bridge_mode=ClimateBridgeMode.MANAGED,
        )

        self.assertEqual("hausman-hub-climate-readiness", result["contract"]["name"])
        self.assertEqual(1, result["contract"]["version"])
        self.assertEqual("managed", result["bridge_mode"])
        self.assertEqual("ready", result["status"])
        self.assertTrue(result["ready"])
        self.assertTrue(result["fresh"])
        self.assertEqual([], result["reasons"])
        # Native reconciliation covers only configured devices: the
        # bridge-only humidifier cannot appear as an unregistered source.
        self.assertEqual(
            {
                "matches": True,
                "matched_device_count": 3,
                "missing_device_count": 0,
                "room_mismatch_device_count": 0,
                "unregistered_source_count": 0,
            },
            result["reconciliation"],
        )

    def test_disabled_mode_never_reads_observation(self) -> None:
        registry, contours, legacy = _setup()
        bound, _ = _native_observation(registry, contours)

        result = native_climate_readiness(
            bound,
            None,
            bridge_mode=ClimateBridgeMode.DISABLED,
        )

        self.assertEqual("disabled", result["status"])
        self.assertFalse(result["fresh"])
        self.assertIsNone(result["reconciliation"])
        self.assertEqual(["bridge_disabled"], result["reasons"])

    def test_missing_observation_is_unavailable(self) -> None:
        registry, contours, legacy = _setup()
        bound, _ = _native_observation(registry, contours)

        result = native_climate_readiness(
            bound,
            None,
            bridge_mode=ClimateBridgeMode.MANAGED,
        )

        self.assertEqual("unavailable", result["status"])
        self.assertEqual(["climate_state_unavailable"], result["reasons"])

    def test_stale_observation_reports_state_stale(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        stale = _with_data_status(observation, ClimateDataStatus.STALE)

        result = native_climate_readiness(
            bound,
            stale,
            bridge_mode=ClimateBridgeMode.MANAGED,
        )

        self.assertEqual("not_ready", result["status"])
        self.assertFalse(result["fresh"])
        self.assertIn("state_stale", result["reasons"])


class NativeApplyPreviewTest(unittest.TestCase):
    """The native apply preview keeps the legacy shape and fails closed."""

    def test_in_sync_contour_reports_no_commands(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        contour = contours.contour("climate")

        legacy_result = _legacy_contour_apply_preview(contour, legacy)
        result = native_contour_apply_preview(
            contour,
            bound,
            ClimateBridgeMode.MANAGED,
            observation,
            fingerprint=contour_fingerprint(contour),
        )

        self.assertEqual(legacy_result["contract"], result["contract"])
        self.assertEqual(legacy_result["contour_id"], result["contour_id"])
        # Semantic difference locked by this golden test: the legacy preview
        # counted bridge sync commands (0, "in_sync"), while the native
        # preview reports the real strict HA plan for the same inputs (one
        # hvac-mode call, "ready").
        self.assertEqual("ready", result["status"])
        self.assertTrue(result["ready"])
        self.assertEqual(1, result["room_count"])
        self.assertEqual(1, result["command_count"])
        self.assertEqual(
            {"temperature": 0, "strategy": 0, "automatic_mode": 0},
            result["changes"],
        )
        self.assertEqual(legacy_result["parameters"], result["parameters"])
        self.assertEqual(legacy_result["limitations"], result["limitations"])
        self.assertEqual(
            legacy_result["requires_confirmation"],
            result["requires_confirmation"],
        )

    def test_missing_room_observation_raises_the_legacy_violation(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        contour = contours.contour("climate")
        partial = type(observation)(
            observed_at=observation.observed_at,
            source_generated_at=observation.source_generated_at,
            data_status=observation.data_status,
            home=observation.home,
            control=observation.control,
            rooms=(),
            devices=(),
        )

        with self.assertRaises(ContourApplyViolation):
            native_contour_apply_preview(
                contour,
                bound,
                ClimateBridgeMode.MANAGED,
                partial,
                fingerprint=contour_fingerprint(contour),
            )


class NativeFailClosedTest(unittest.TestCase):
    """Missing or stale native evidence never becomes permissive."""

    def test_command_types_come_only_from_validated_bindings(self) -> None:
        registry, contours, legacy = _setup()
        bound, _ = _native_observation(registry, contours)
        ac = bound.device("living_air_conditioner")
        temperature_sensor = bound.device("living_temperature_observation")

        self.assertEqual(
            {
                "climate.turn_off",
                "climate.set_hvac_mode",
                "climate.set_temperature",
                "climate.set_fan_mode",
            },
            set(native_device_command_types(ac)),
        )
        self.assertEqual((), native_device_command_types(temperature_sensor))

    def test_stale_observation_blocks_control_and_marks_contour_stale(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        stale = _with_data_status(observation, ClimateDataStatus.STALE)

        android = native_android_climate_snapshot(
            bound,
            stale,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )
        contour_result = native_contour_snapshot(
            contours,
            bound,
            stale,
            settings_apply_enabled=True,
        )

        self.assertFalse(android["climate"]["fresh"])
        self.assertEqual("stale", android["rooms"][0]["actual"]["data_status"])
        self.assertIn(
            "state_stale", android["rooms"][0]["control"]["blocked_reasons"]
        )
        self.assertEqual([], android["rooms"][0]["control"]["allowed_actions"])
        self.assertEqual("stale", contour_result["contours"][0]["status"])
        self.assertFalse(
            contour_result["contours"][0]["execution"]["settings_apply"]["available"]
        )

    def test_missing_device_observation_marks_device_unavailable(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        devices = tuple(
            device
            for device in observation.devices
            if device.device_id != "living_air_conditioner"
        )
        partial = type(observation)(
            observed_at=observation.observed_at,
            source_generated_at=observation.source_generated_at,
            data_status=observation.data_status,
            home=observation.home,
            control=observation.control,
            rooms=observation.rooms,
            devices=devices,
        )

        android = native_android_climate_snapshot(
            bound,
            partial,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )

        living = android["rooms"][0]
        ac = next(
            device
            for device in living["devices"]
            if device["id"] == "living_air_conditioner"
        )
        self.assertFalse(ac["available"])
        self.assertEqual("unavailable", ac["state"])
        self.assertEqual(
            ["living_air_conditioner"],
            android["reconciliation"]["missing_device_ids"],
        )
        self.assertFalse(android["reconciliation"]["matches"])


class NativeReadinessHardeningTest(unittest.TestCase):
    """Readiness never reports ready without full native coverage."""

    def test_missing_room_observation_is_not_ready(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        partial = type(observation)(
            observed_at=observation.observed_at,
            source_generated_at=observation.source_generated_at,
            data_status=observation.data_status,
            home=observation.home,
            control=observation.control,
            rooms=(),
            devices=(),
        )

        result = native_climate_readiness(
            bound,
            partial,
            bridge_mode=ClimateBridgeMode.MANAGED,
        )

        self.assertEqual("not_ready", result["status"])
        self.assertFalse(result["ready"])
        self.assertIn("registry_mismatch", result["reasons"])
        self.assertIn("device_unavailable", result["reasons"])

    def test_unavailable_device_blocks_readiness(self) -> None:
        registry, contours, legacy = _setup()
        bound, observation = _native_observation(registry, contours)
        devices = tuple(
            device
            for device in observation.devices
            if device.device_id != "living_temperature_observation"
        )
        partial = type(observation)(
            observed_at=observation.observed_at,
            source_generated_at=observation.source_generated_at,
            data_status=observation.data_status,
            home=observation.home,
            control=observation.control,
            rooms=observation.rooms,
            devices=devices,
        )

        result = native_climate_readiness(
            bound,
            partial,
            bridge_mode=ClimateBridgeMode.MANAGED,
        )

        self.assertEqual("not_ready", result["status"])
        self.assertIn("device_unavailable", result["reasons"])


class NativeControlGateTest(unittest.TestCase):
    """The room control gate opens only with complete native evidence."""

    def _android(self, observation, **overrides):
        registry, contours, _ = _setup()
        bound, _ = _native_observation(registry, contours)
        arguments = {
            "contours": contours,
            "bridge_mode": ClimateBridgeMode.CANARY,
            "canary_room_id": "living",
            "candidate_ready": True,
        }
        arguments.update(overrides)
        return native_android_climate_snapshot(bound, observation, **arguments)

    def test_canary_room_control_opens_with_full_native_evidence(self) -> None:
        registry, contours, _ = _setup()
        _, observation = _native_observation(registry, contours)

        result = self._android(observation)
        control = result["rooms"][0]["control"]

        self.assertTrue(result["climate"]["commands_enabled"])
        self.assertTrue(control["enabled"])
        self.assertEqual(
            ["set_room_target", "turn_room_off"], control["allowed_actions"]
        )
        self.assertEqual([], control["blocked_reasons"])

    def test_canary_room_control_closes_on_each_single_mutation(self) -> None:
        registry, contours, _ = _setup()
        _, observation = _native_observation(registry, contours)

        stale = self._android(
            _with_data_status(observation, ClimateDataStatus.STALE)
        )["rooms"][0]["control"]
        self.assertFalse(stale["enabled"])
        self.assertIn("state_stale", stale["blocked_reasons"])

        without_evidence = self._android(observation, candidate_ready=False)[
            "rooms"
        ][0]["control"]
        self.assertFalse(without_evidence["enabled"])
        self.assertIn(
            "evidence_not_ready", without_evidence["blocked_reasons"]
        )

        pending = self._android(observation, pending_room_ids=("living",))[
            "rooms"
        ][0]["control"]
        self.assertFalse(pending["enabled"])
        self.assertIn("operation_pending", pending["blocked_reasons"])

        missing_device = type(observation)(
            observed_at=observation.observed_at,
            source_generated_at=observation.source_generated_at,
            data_status=observation.data_status,
            home=observation.home,
            control=observation.control,
            rooms=observation.rooms,
            devices=tuple(
                device
                for device in observation.devices
                if device.device_id != "living_air_conditioner"
            ),
        )
        missing = self._android(missing_device)["rooms"][0]["control"]
        self.assertFalse(missing["enabled"])
        self.assertIn("registry_mismatch", missing["blocked_reasons"])


class NativeGoldenContractTest(unittest.TestCase):
    """Lock serialization stability that parity normalization cannot catch."""

    def test_state_revision_is_stable_for_identical_inputs(self) -> None:
        registry, contours, _ = _setup()
        bound, observation = _native_observation(registry, contours)

        first = native_android_climate_snapshot(
            bound,
            observation,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )
        second = native_android_climate_snapshot(
            bound,
            observation,
            contours=contours,
            bridge_mode=ClimateBridgeMode.SHADOW,
        )

        self.assertEqual(first["state_revision"], second["state_revision"])
        self.assertEqual(first, second)

    def test_admin_command_types_keep_a_stable_contract_order(self) -> None:
        registry, contours, _ = _setup()
        bound, observation = _native_observation(registry, contours)

        result = native_admin_climate_import_snapshot(bound, observation)
        candidates = {
            item["source_id"]: item for item in result["candidates"]
        }

        self.assertEqual(
            [
                "climate.turn_off",
                "climate.set_temperature",
                "climate.set_hvac_mode",
                "climate.set_fan_mode",
            ],
            candidates["synthetic-ac-source-living"]["command_types"],
        )
        self.assertEqual(
            [],
            candidates["synthetic-living_temperature_observation"][
                "command_types"
            ],
        )
