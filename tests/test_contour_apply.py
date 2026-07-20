"""Pure tests for confirmed HausmanHub contour settings application."""

from __future__ import annotations

import unittest

from custom_components.hausman_hub.application.climate_import import (
    import_climate_state,
)
from custom_components.hausman_hub.application.contour_apply import (
    ContourApplyViolation,
    build_contour_apply_plan,
    confirmed_contour_room_count,
    parse_contour_apply_request,
)
from custom_components.hausman_hub.application.contour_override import (
    TemporaryTemperatureAction,
    TemporaryTemperatureViolation,
    parse_temporary_temperature_request,
)
from custom_components.hausman_hub.application.contours import (
    with_climate_contour_mode,
)
from tests.test_contours import setup, source_payload, source_snapshot


class ContourApplyTest(unittest.TestCase):
    def test_plan_uses_only_three_typed_existing_engine_commands(self) -> None:
        registry, contours = setup()
        payload = source_payload()
        payload["rooms"][0]["mode"] = "manual"  # type: ignore[index]
        payload["rooms"][0]["targets"]["temperature"] = 26  # type: ignore[index]
        payload["rooms"][0]["targets"]["targetStrategy"] = "soft"  # type: ignore[index]
        snapshot = import_climate_state(
            payload,
            now_ms=payload["generatedAt"] + 1_000,  # type: ignore[operator]
        )

        plan = build_contour_apply_plan(
            contours.contour("climate"),  # type: ignore[arg-type]
            registry,
            snapshot,
        )

        self.assertEqual(
            (
                "set_room_target_strategy",
                "set_room_target",
                "set_room_mode",
            ),
            tuple(command.action for command in plan.commands),
        )
        self.assertTrue(all(command.execute for command in plan.commands))
        self.assertEqual(1, plan.strategy_changes)
        self.assertEqual(1, plan.temperature_changes)
        self.assertEqual(1, plan.automatic_mode_changes)
        self.assertNotIn("humidity", str([item.backend_payload for item in plan.commands]))

    def test_matching_contour_needs_no_post_and_is_observably_confirmed(self) -> None:
        registry, contours = setup()
        snapshot = source_snapshot()

        plan = build_contour_apply_plan(
            contours.contour("climate"),  # type: ignore[arg-type]
            registry,
            snapshot,
        )

        self.assertEqual((), plan.commands)
        self.assertEqual("in_sync", plan.preview_payload()["status"])
        self.assertEqual(1, confirmed_contour_room_count(plan, snapshot))

    def test_apply_requires_automatic_mode_fresh_state_and_available_device(self) -> None:
        registry, contours = setup()
        observe = with_climate_contour_mode(contours, "observe")
        with self.assertRaisesRegex(ContourApplyViolation, "automatic"):
            build_contour_apply_plan(
                observe.contour("climate"),  # type: ignore[arg-type]
                registry,
                source_snapshot(),
            )

        stale_payload = source_payload()
        stale_payload["runtimeHealth"]["status"] = "stale"  # type: ignore[index]
        stale = import_climate_state(stale_payload)
        with self.assertRaisesRegex(ContourApplyViolation, "stale"):
            build_contour_apply_plan(
                contours.contour("climate"),  # type: ignore[arg-type]
                registry,
                stale,
            )

        unavailable_payload = source_payload()
        unavailable_payload["devices"][0]["unavailable"] = True  # type: ignore[index]
        unavailable = import_climate_state(unavailable_payload)
        with self.assertRaisesRegex(ContourApplyViolation, "device"):
            build_contour_apply_plan(
                contours.contour("climate"),  # type: ignore[arg-type]
                registry,
                unavailable,
            )

    def test_request_requires_exact_explicit_confirmation(self) -> None:
        self.assertEqual(
            ("android-1", "climate"),
            parse_contour_apply_request(
                {
                    "request_id": "android-1",
                    "contour_id": "climate",
                    "confirm": True,
                }
            ),
        )
        for invalid in (
            {"request_id": "android-1", "contour_id": "climate"},
            {
                "request_id": "android-1",
                "contour_id": "climate",
                "confirm": False,
            },
            {
                "request_id": "android-1",
                "contour_id": "climate",
                "confirm": True,
                "command": "raw",
            },
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                ContourApplyViolation
            ):
                parse_contour_apply_request(invalid)

    def test_temporary_temperature_request_is_bounded_and_explicit(self) -> None:
        request = parse_temporary_temperature_request(
            {
                "request_id": "temporary-1",
                "contour_id": "climate",
                "room_id": "living",
                "action": "set",
                "target_temperature": 23.5,
                "confirm": True,
            }
        )

        self.assertIs(request.action, TemporaryTemperatureAction.SET)
        self.assertEqual(23.5, request.target_temperature)
        clear = parse_temporary_temperature_request(
            {
                "request_id": "temporary-clear-1",
                "contour_id": "climate",
                "room_id": "living",
                "action": "clear",
                "target_temperature": None,
                "confirm": True,
            }
        )
        self.assertIs(clear.action, TemporaryTemperatureAction.CLEAR)
        self.assertIsNone(clear.target_temperature)

        base = {
            "request_id": "temporary-2",
            "contour_id": "climate",
            "room_id": "living",
            "action": "set",
            "target_temperature": 23.5,
            "confirm": True,
        }
        for invalid in (
            {**base, "confirm": False},
            {**base, "target_temperature": 23.2},
            {**base, "target_temperature": 29.0},
            {**base, "duration": 60},
            {**base, "action": "raw"},
            {**base, "action": "clear"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                TemporaryTemperatureViolation
            ):
                parse_temporary_temperature_request(invalid)


if __name__ == "__main__":
    unittest.main()
