"""Pure tests for bounded redacted climate shadow evidence."""

from __future__ import annotations

import json
import unittest

from custom_components.hausman_hub.application.climate_evidence import (
    ClimateEvidenceViolation,
    ClimateShadowEvidence,
    candidate_room_from_payload,
    evidence_from_storage_payload,
)
from custom_components.hausman_hub.application.climate_import import import_climate_state
from custom_components.hausman_hub.application.climate_registry import registry_from_payload
from custom_components.hausman_hub.domain.climate_bridge import ClimateBridgeMode
from tests.test_climate_import import registry_payload, source_payload


NOW = 1784280605000


class ClimateShadowEvidenceTest(unittest.TestCase):
    def test_matching_window_and_two_required_intents_make_one_room_ready(self) -> None:
        registry = registry_from_payload(registry_payload())
        snapshot = import_climate_state(source_payload())
        evidence = ClimateShadowEvidence.for_registry(
            registry,
            now_ms=NOW - 600_000,
        )
        for offset in (600_000, 300_000, 0):
            evidence.record_observation(
                registry,
                snapshot,
                now_ms=NOW - offset,
            )
        for action in ("set_room_target", "turn_room_off"):
            evidence.record_intent(
                category="translated",
                room_id="living",
                action=action,
                now_ms=NOW,
            )

        payload = evidence.as_payload(
            registry=registry,
            snapshot=snapshot,
            bridge_mode=ClimateBridgeMode.SHADOW,
            candidate_room_id="living",
            now_ms=NOW,
        )

        candidate = payload["candidate"]
        self.assertTrue(candidate["ready"])  # type: ignore[index]
        self.assertEqual("ready", candidate["status"])  # type: ignore[index]
        self.assertEqual(3, candidate["matched_observation_count"])  # type: ignore[index]
        self.assertEqual(2, candidate["translated_action_count"])  # type: ignore[index]
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("source_id", serialized)
        self.assertNotIn("entity_id", serialized)
        self.assertNotIn("synthetic-ac-source", serialized)

    def test_anomaly_or_registry_change_blocks_and_resets_evidence(self) -> None:
        registry = registry_from_payload(registry_payload())
        moved = source_payload()
        moved["devices"][0]["roomId"] = "kids"  # type: ignore[index]
        snapshot = import_climate_state(moved)
        evidence = ClimateShadowEvidence.for_registry(registry, now_ms=NOW)
        evidence.record_observation(registry, snapshot, now_ms=NOW)

        payload = evidence.as_payload(
            registry=registry,
            snapshot=snapshot,
            bridge_mode=ClimateBridgeMode.SHADOW,
            candidate_room_id="living",
            now_ms=NOW,
        )

        candidate = payload["candidate"]
        self.assertEqual("blocked", candidate["status"])  # type: ignore[index]
        self.assertIn("registry_mismatch", candidate["reasons"])  # type: ignore[index]
        self.assertIn("shadow_anomalies_observed", candidate["reasons"])  # type: ignore[index]

        changed = registry_payload()
        changed["rooms"][0]["name"] = "Renamed"  # type: ignore[index]
        self.assertTrue(
            evidence.ensure_registry(
                registry_from_payload(changed),
                now_ms=NOW + 1,
            )
        )
        self.assertEqual([], evidence.observations)
        self.assertEqual([], evidence.intents)

    def test_storage_round_trip_is_exact_bounded_and_candidate_query_is_strict(self) -> None:
        registry = registry_from_payload(registry_payload())
        snapshot = import_climate_state(source_payload())
        evidence = ClimateShadowEvidence.for_registry(registry, now_ms=NOW)
        evidence.record_observation(registry, snapshot, now_ms=NOW)
        restored = evidence_from_storage_payload(evidence.as_storage_payload())

        self.assertEqual(evidence.as_storage_payload(), restored.as_storage_payload())
        self.assertEqual("living", candidate_room_from_payload({"room_id": "living"}))
        for invalid in (
            {},
            {"room_id": "living", "source_id": "private"},
            {"room_id": "Living room"},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ClimateEvidenceViolation):
                    candidate_room_from_payload(invalid)


if __name__ == "__main__":
    unittest.main()
