"""Safe room suggestions for HausmanHub climate device candidates."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from custom_components.hausman_hub.application.climate_import import (
    import_climate_state,
)
from custom_components.hausman_hub.application.climate_registry import (
    registry_from_payload,
)
from custom_components.hausman_hub.application.climate_setup import (
    climate_room_suggestions,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = ROOT / "fixtures" / "climate_bridge" / "valid_state.json"
REGISTRY_FIXTURE = ROOT / "fixtures" / "hausmanhub_climate_v1" / "registry.json"
SUGGESTIONS_FIXTURE = (
    ROOT / "fixtures" / "hausmanhub_climate_room_suggestions_v1" / "suggestions.json"
)
SUGGESTIONS_SCHEMA = (
    ROOT
    / "custom_components"
    / "hausman_hub"
    / "contracts"
    / "v1"
    / "climate-room-suggestions.schema.json"
)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def living_ac_registry() -> object:
    payload = copy.deepcopy(load_json(REGISTRY_FIXTURE))
    payload["rooms"] = [  # type: ignore[index]
        room for room in payload["rooms"] if room["id"] == "living"  # type: ignore[index]
    ]
    payload["devices"] = [  # type: ignore[index]
        device
        for device in payload["devices"]  # type: ignore[index]
        if device["id"] == "living_ac"
    ]
    return registry_from_payload(payload)


class ClimateSetupSuggestionsTest(unittest.TestCase):
    """Suggest explicit source rooms without silently changing assignments."""

    def setUp(self) -> None:
        schema = load_json(SUGGESTIONS_SCHEMA)
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def test_exact_source_room_is_suggested_and_requires_confirmation(self) -> None:
        result = climate_room_suggestions(
            living_ac_registry(),  # type: ignore[arg-type]
            import_climate_state(load_json(SOURCE_FIXTURE)),
        )

        self.validator.validate(result)
        self.assertEqual(load_json(SUGGESTIONS_FIXTURE), result)
        self.assertTrue(result["confirmation_required"])
        self.assertTrue(result["assignment_allowed"])
        serialized = json.dumps(result, ensure_ascii=True, sort_keys=True)
        self.assertNotIn("source_id", serialized)
        self.assertNotIn("entity_id", serialized)
        self.assertNotIn("synthetic-humidifier-source-kids", serialized)

    def test_device_name_never_overrides_its_explicit_source_room(self) -> None:
        misleading = copy.deepcopy(load_json(SOURCE_FIXTURE))
        humidifier = next(  # type: ignore[call-overload]
            device
            for device in misleading["devices"]  # type: ignore[index]
            if device["id"] == "synthetic-humidifier-source-kids"
        )
        humidifier["name"] = "Увлажнитель гостиной"

        result = climate_room_suggestions(
            living_ac_registry(),  # type: ignore[arg-type]
            import_climate_state(misleading),
        )

        suggestion = next(
            value
            for value in result["suggestions"]
            if value["device_name"] == "Увлажнитель гостиной"
        )
        self.assertEqual("kids", suggestion["suggested_room_id"])
        self.assertEqual("detected_room", suggestion["reason"])
        self.assertTrue(suggestion["can_accept"])

    def test_stale_data_removes_every_room_suggestion(self) -> None:
        stale = copy.deepcopy(load_json(SOURCE_FIXTURE))
        stale["runtimeHealth"]["status"] = "stale"  # type: ignore[index]

        result = climate_room_suggestions(
            living_ac_registry(),  # type: ignore[arg-type]
            import_climate_state(stale),
        )

        self.validator.validate(result)
        self.assertFalse(result["assignment_allowed"])
        for suggestion in result["suggestions"]:
            self.assertIsNone(suggestion["suggested_room_id"])
            self.assertIsNone(suggestion["suggested_room_name"])
            self.assertEqual("none", suggestion["confidence"])
            self.assertEqual("data_stale", suggestion["reason"])
            self.assertFalse(suggestion["can_accept"])

    def test_registry_mismatch_is_not_turned_into_a_guess(self) -> None:
        moved = copy.deepcopy(load_json(SOURCE_FIXTURE))
        living = next(  # type: ignore[call-overload]
            device
            for device in moved["devices"]  # type: ignore[index]
            if device["id"] == "synthetic-ac-source-living"
        )
        living["roomId"] = "kids"

        result = climate_room_suggestions(
            living_ac_registry(),  # type: ignore[arg-type]
            import_climate_state(moved),
        )

        self.validator.validate(result)
        suggestion = next(
            value
            for value in result["suggestions"]
            if value["device_name"] == "Living AC"
        )
        self.assertEqual("registry_mismatch", suggestion["candidate_status"])
        self.assertIsNone(suggestion["suggested_room_id"])
        self.assertEqual("none", suggestion["confidence"])
        self.assertFalse(suggestion["can_accept"])

    def test_schema_requires_explicit_confirmation_and_consistent_acceptance(self) -> None:
        no_confirmation = copy.deepcopy(load_json(SUGGESTIONS_FIXTURE))
        no_confirmation["confirmation_required"] = False  # type: ignore[index]
        with self.assertRaises(Exception):
            self.validator.validate(no_confirmation)

        unsafe_acceptance = copy.deepcopy(load_json(SUGGESTIONS_FIXTURE))
        suggestion = unsafe_acceptance["suggestions"][0]  # type: ignore[index]
        suggestion["suggested_room_id"] = None
        suggestion["suggested_room_name"] = None
        suggestion["confidence"] = "none"
        with self.assertRaises(Exception):
            self.validator.validate(unsafe_acceptance)

        guessed_mismatch = copy.deepcopy(load_json(SUGGESTIONS_FIXTURE))
        mismatch = guessed_mismatch["suggestions"][1]  # type: ignore[index]
        mismatch["candidate_status"] = "registry_mismatch"
        mismatch["reason"] = "registry_mismatch"
        with self.assertRaises(Exception):
            self.validator.validate(guessed_mismatch)


if __name__ == "__main__":
    unittest.main()
