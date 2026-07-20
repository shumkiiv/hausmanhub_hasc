"""Pure tests for HausmanHub logical climate rooms and devices."""

from __future__ import annotations

import unittest

from custom_components.hausman_hub.domain.climate import (
    ClimateCapability,
    ClimateControlOwner,
    ClimateControlScope,
    ClimateDevice,
    ClimateDeviceKind,
    ClimateEndpoint,
    ClimateEndpointRole,
    ClimateModelViolation,
    ClimateRegistry,
    ClimateRoom,
)


def air_conditioner(**changes: object) -> ClimateDevice:
    """Build one safe synthetic AC registration."""

    values: dict[str, object] = {
        "device_id": "living_ac",
        "name": "Living AC",
        "room_id": "living",
        "kind": ClimateDeviceKind.AIR_CONDITIONER,
        "source_id": "synthetic-climate-source-living",
        "control_scope": ClimateControlScope.CANARY,
        "control_owner": ClimateControlOwner.CLIMATE_CORE,
        "capabilities": (
            ClimateCapability.POWER,
            ClimateCapability.TARGET_TEMPERATURE,
            ClimateCapability.HVAC_MODE,
            ClimateCapability.FAN_MODE,
            ClimateCapability.PHYSICAL_FEEDBACK,
        ),
        "endpoints": (
            ClimateEndpoint(
                ClimateEndpointRole.CONTROL,
                "climate.synthetic_living_ac",
            ),
            ClimateEndpoint(
                ClimateEndpointRole.PHYSICAL_FEEDBACK,
                "binary_sensor.synthetic_living_ac_flap",
            ),
        ),
    }
    values.update(changes)
    return ClimateDevice(**values)  # type: ignore[arg-type]


class ClimateRegistryTest(unittest.TestCase):
    """Keep configuration typed, explicit, and free of generic proxy fields."""

    def test_registry_groups_private_endpoints_under_one_logical_device(self) -> None:
        registry = ClimateRegistry(
            rooms=(ClimateRoom("living", "Living room"),),
            devices=(air_conditioner(),),
        )

        device = registry.device("living_ac")

        self.assertIsNotNone(device)
        assert device is not None
        self.assertTrue(device.supports(ClimateCapability.TARGET_TEMPERATURE))
        self.assertEqual(
            "binary_sensor.synthetic_living_ac_flap",
            device.endpoint(ClimateEndpointRole.PHYSICAL_FEEDBACK).entity_id,
        )

    def test_every_climate_kind_has_an_explicit_minimum_contract(self) -> None:
        devices = (
            air_conditioner(),
            air_conditioner(
                device_id="bedroom_trv",
                name="Bedroom TRV",
                room_id="bedroom",
                kind=ClimateDeviceKind.RADIATOR_THERMOSTAT,
                source_id="synthetic-trv-source-bedroom",
                capabilities=(ClimateCapability.TARGET_TEMPERATURE,),
                endpoints=(
                    ClimateEndpoint(
                        ClimateEndpointRole.CONTROL,
                        "climate.synthetic_bedroom_trv",
                    ),
                ),
            ),
            air_conditioner(
                device_id="kids_humidifier",
                name="Kids humidifier",
                room_id="kids",
                kind=ClimateDeviceKind.HUMIDIFIER,
                source_id="synthetic-humidifier-source-kids",
                capabilities=(
                    ClimateCapability.POWER,
                    ClimateCapability.TARGET_HUMIDITY,
                ),
                endpoints=(
                    ClimateEndpoint(
                        ClimateEndpointRole.CONTROL,
                        "humidifier.synthetic_kids",
                    ),
                ),
            ),
            air_conditioner(
                device_id="bathroom_floor",
                name="Bathroom floor",
                room_id="bathroom",
                kind=ClimateDeviceKind.FLOOR_HEATING,
                source_id="synthetic-floor-source-bathroom",
                capabilities=(
                    ClimateCapability.POWER,
                    ClimateCapability.TARGET_TEMPERATURE,
                ),
                endpoints=(
                    ClimateEndpoint(
                        ClimateEndpointRole.CONTROL,
                        "climate.synthetic_bathroom_floor",
                    ),
                ),
            ),
        )

        registry = ClimateRegistry(
            rooms=(
                ClimateRoom("living", "Living room"),
                ClimateRoom("bedroom", "Bedroom"),
                ClimateRoom("kids", "Kids"),
                ClimateRoom("bathroom", "Bathroom"),
            ),
            devices=devices,
        )

        self.assertEqual(4, len(registry.devices))

    def test_passive_sensor_cannot_gain_a_control_surface(self) -> None:
        with self.assertRaisesRegex(ClimateModelViolation, "must not have"):
            air_conditioner(
                device_id="living_temperature",
                name="Living temperature",
                kind=ClimateDeviceKind.TEMPERATURE_SENSOR,
                source_id="synthetic-temperature-source",
                capabilities=(),
                control_scope=ClimateControlScope.OBSERVED,
                control_owner=ClimateControlOwner.OBSERVED,
                endpoints=(
                    ClimateEndpoint(
                        ClimateEndpointRole.CONTROL,
                        "sensor.synthetic_living_temperature",
                    ),
                ),
            )

    def test_observed_device_cannot_hide_an_active_owner(self) -> None:
        with self.assertRaisesRegex(ClimateModelViolation, "observed ownership"):
            air_conditioner(
                control_scope=ClimateControlScope.OBSERVED,
                control_owner=ClimateControlOwner.CLIMATE_CORE,
            )

    def test_registry_rejects_duplicate_sources_and_unknown_rooms(self) -> None:
        with self.assertRaisesRegex(ClimateModelViolation, "source ids"):
            ClimateRegistry(
                rooms=(ClimateRoom("living", "Living room"),),
                devices=(
                    air_conditioner(),
                    air_conditioner(device_id="second_ac", name="Second AC"),
                ),
            )

        with self.assertRaisesRegex(ClimateModelViolation, "unknown rooms"):
            ClimateRegistry(
                rooms=(ClimateRoom("living", "Living room"),),
                devices=(air_conditioner(room_id="missing"),),
            )

    def test_required_capabilities_and_endpoint_shape_fail_closed(self) -> None:
        with self.assertRaisesRegex(ClimateModelViolation, "required capabilities"):
            air_conditioner(capabilities=(ClimateCapability.POWER,))

        with self.assertRaisesRegex(ClimateModelViolation, "one control endpoint"):
            air_conditioner(endpoints=())

        with self.assertRaisesRegex(ClimateModelViolation, "Home Assistant entity"):
            ClimateEndpoint(ClimateEndpointRole.CONTROL, "not an entity")


if __name__ == "__main__":
    unittest.main()
