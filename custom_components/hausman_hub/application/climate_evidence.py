"""Bounded, redacted shadow evidence for one future climate canary.

The ledger stores only public HASC room IDs, approved action names, timestamps,
and coarse categories. Private source IDs, entity IDs, payloads, targets, and
backend responses never enter either the persisted or administrator contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from ..domain.climate import ClimateRegistry, ClimateRoom
from ..domain.climate_bridge import ClimateBridgeMode
from .climate_commands import ClimateCommandViolation, plan_climate_command
from .climate_import import ClimateImportSnapshot
from .climate_registry import reconcile_climate_registry, registry_to_payload


SHADOW_EVIDENCE_CONTRACT_NAME = "hausman-hasc-climate-shadow-evidence"
SHADOW_EVIDENCE_CONTRACT_VERSION = 1
SHADOW_EVIDENCE_STORAGE_VERSION = 1
SHADOW_EVIDENCE_WINDOW_MS = 24 * 60 * 60 * 1000
SHADOW_EVIDENCE_SAMPLE_INTERVAL_MS = 5 * 60 * 1000
SHADOW_EVIDENCE_MAX_OBSERVATIONS = (
    SHADOW_EVIDENCE_WINDOW_MS // SHADOW_EVIDENCE_SAMPLE_INTERVAL_MS
)
SHADOW_EVIDENCE_MAX_INTENTS = 512
SHADOW_EVIDENCE_MIN_MATCHED_OBSERVATIONS = 3
SHADOW_EVIDENCE_REQUIRED_ACTIONS = (
    "set_room_target",
    "turn_room_off",
)

_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
_INTENT_CATEGORIES = frozenset({"translated", "rejected"})
_APPROVED_ACTIONS = frozenset(
    {
        "set_room_target",
        "set_room_mode",
        "set_room_min_target",
        "set_room_target_strategy",
        "turn_room_off",
        "set_device_power",
        "set_device_target_temperature",
        "set_device_target_humidity",
        "set_device_hvac_mode",
        "set_device_fan_mode",
    }
)


class ClimateEvidenceViolation(ValueError):
    """Persisted or requested shadow evidence is outside the fixed contract."""


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    """One sampled reconciliation result without device identifiers."""

    observed_at: int
    matched_rooms: tuple[str, ...]
    missing_rooms: tuple[str, ...]
    moved_rooms: tuple[str, ...]
    stale: bool
    unregistered_sources: bool


@dataclass(frozen=True, slots=True)
class ShadowIntent:
    """One coarse translated or rejected tablet intent."""

    observed_at: int
    category: str
    room_id: str | None
    action: str | None


class ClimateShadowEvidence:
    """Maintain a rolling evidence window bound to one exact registry."""

    def __init__(
        self,
        *,
        registry_fingerprint: str,
        window_started_at: int,
        observations: tuple[ShadowObservation, ...] = (),
        intents: tuple[ShadowIntent, ...] = (),
    ) -> None:
        if not isinstance(registry_fingerprint, str) or not _FINGERPRINT.fullmatch(
            registry_fingerprint
        ):
            raise ClimateEvidenceViolation("evidence registry fingerprint is invalid")
        _safe_timestamp(window_started_at, "evidence window start")
        if len(observations) > SHADOW_EVIDENCE_MAX_OBSERVATIONS:
            raise ClimateEvidenceViolation("evidence observations are not bounded")
        if len(intents) > SHADOW_EVIDENCE_MAX_INTENTS:
            raise ClimateEvidenceViolation("evidence intents are not bounded")
        timestamps = tuple(
            value.observed_at for value in (*observations, *intents)
        )
        if any(value < window_started_at for value in timestamps):
            raise ClimateEvidenceViolation("evidence predates its rolling window")
        if tuple(value.observed_at for value in observations) != tuple(
            sorted(value.observed_at for value in observations)
        ):
            raise ClimateEvidenceViolation("evidence observations are not ordered")
        if tuple(value.observed_at for value in intents) != tuple(
            sorted(value.observed_at for value in intents)
        ):
            raise ClimateEvidenceViolation("evidence intents are not ordered")
        self.registry_fingerprint = registry_fingerprint
        self.window_started_at = window_started_at
        self.observations = list(observations)
        self.intents = list(intents)

    @classmethod
    def for_registry(
        cls,
        registry: ClimateRegistry,
        *,
        now_ms: int,
    ) -> ClimateShadowEvidence:
        """Create an empty window tied to the exact validated registry."""

        _safe_timestamp(now_ms, "evidence clock")
        return cls(
            registry_fingerprint=_registry_fingerprint(registry),
            window_started_at=now_ms,
        )

    def ensure_registry(self, registry: ClimateRegistry, *, now_ms: int) -> bool:
        """Reset evidence when any private or public registry binding changes."""

        fingerprint = _registry_fingerprint(registry)
        if fingerprint == self.registry_fingerprint:
            return self.prune(now_ms=now_ms)
        _safe_timestamp(now_ms, "evidence clock")
        self.registry_fingerprint = fingerprint
        self.window_started_at = now_ms
        self.observations.clear()
        self.intents.clear()
        return True

    def record_observation(
        self,
        registry: ClimateRegistry,
        snapshot: ClimateImportSnapshot,
        *,
        now_ms: int,
    ) -> bool:
        """Sample reconciliation at most once per fixed five-minute interval."""

        changed = self.ensure_registry(registry, now_ms=now_ms)
        if (
            self.observations
            and now_ms - self.observations[-1].observed_at
            < SHADOW_EVIDENCE_SAMPLE_INTERVAL_MS
        ):
            return changed

        matched: list[str] = []
        missing: list[str] = []
        moved: list[str] = []
        reconciliation = reconcile_climate_registry(registry, snapshot)
        missing_devices = set(reconciliation.missing_device_ids)
        moved_devices = set(reconciliation.room_mismatch_device_ids)
        for room in registry.rooms:
            room_devices = tuple(
                device for device in registry.devices if device.room_id == room.room_id
            )
            if not room_devices or any(
                device.device_id in missing_devices for device in room_devices
            ):
                missing.append(room.room_id)
            elif any(device.device_id in moved_devices for device in room_devices):
                moved.append(room.room_id)
            else:
                matched.append(room.room_id)

        self.observations.append(
            ShadowObservation(
                observed_at=now_ms,
                matched_rooms=tuple(sorted(matched)),
                missing_rooms=tuple(sorted(missing)),
                moved_rooms=tuple(sorted(moved)),
                stale=not snapshot.runtime_fresh,
                unregistered_sources=bool(reconciliation.unregistered_source_ids),
            )
        )
        if len(self.observations) > SHADOW_EVIDENCE_MAX_OBSERVATIONS:
            del self.observations[: -SHADOW_EVIDENCE_MAX_OBSERVATIONS]
        return True

    def record_intent(
        self,
        *,
        category: str,
        room_id: str | None,
        action: str | None,
        now_ms: int,
    ) -> bool:
        """Record only one approved coarse intent outcome."""

        self.prune(now_ms=now_ms)
        if category not in _INTENT_CATEGORIES:
            raise ClimateEvidenceViolation("evidence intent category is invalid")
        if room_id is not None:
            _validate_room_id(room_id)
        if action is not None and action not in _APPROVED_ACTIONS:
            action = None
        self.intents.append(
            ShadowIntent(
                observed_at=now_ms,
                category=category,
                room_id=room_id,
                action=action,
            )
        )
        if len(self.intents) > SHADOW_EVIDENCE_MAX_INTENTS:
            del self.intents[: -SHADOW_EVIDENCE_MAX_INTENTS]
        return True

    def prune(self, *, now_ms: int) -> bool:
        """Discard data outside the rolling window and reject clock rollback."""

        _safe_timestamp(now_ms, "evidence clock")
        if now_ms < self.window_started_at:
            raise ClimateEvidenceViolation("evidence clock moved before its window")
        if any(
            value.observed_at > now_ms
            for value in (*self.observations, *self.intents)
        ):
            raise ClimateEvidenceViolation("evidence contains a future event")
        cutoff = max(0, now_ms - SHADOW_EVIDENCE_WINDOW_MS)
        observations = [
            value for value in self.observations if value.observed_at >= cutoff
        ]
        intents = [value for value in self.intents if value.observed_at >= cutoff]
        changed = observations != self.observations or intents != self.intents
        self.observations = observations
        self.intents = intents
        if self.window_started_at < cutoff:
            self.window_started_at = cutoff
            changed = True
        return changed

    def as_payload(
        self,
        *,
        registry: ClimateRegistry,
        snapshot: ClimateImportSnapshot | None,
        bridge_mode: ClimateBridgeMode,
        candidate_room_id: str | None,
        now_ms: int,
    ) -> dict[str, object]:
        """Return counts and readiness without private registry bindings."""

        self.prune(now_ms=now_ms)
        return {
            "contract": {
                "name": SHADOW_EVIDENCE_CONTRACT_NAME,
                "version": SHADOW_EVIDENCE_CONTRACT_VERSION,
            },
            "bridge_mode": bridge_mode.value,
            "window": {
                "duration_ms": SHADOW_EVIDENCE_WINDOW_MS,
                "sample_interval_ms": SHADOW_EVIDENCE_SAMPLE_INTERVAL_MS,
                "started_at": self.window_started_at,
                "updated_at": now_ms,
                "observation_count": len(self.observations),
                "intent_count": len(self.intents),
            },
            "counts": self._counts(),
            "candidate": self._candidate_payload(
                registry=registry,
                snapshot=snapshot,
                bridge_mode=bridge_mode,
                room_id=candidate_room_id,
            ),
        }

    def as_storage_payload(self) -> dict[str, object]:
        """Serialize the exact bounded private Store shape."""

        return {
            "version": SHADOW_EVIDENCE_STORAGE_VERSION,
            "registry_fingerprint": self.registry_fingerprint,
            "window_started_at": self.window_started_at,
            "observations": [
                {
                    "observed_at": value.observed_at,
                    "matched_rooms": list(value.matched_rooms),
                    "missing_rooms": list(value.missing_rooms),
                    "moved_rooms": list(value.moved_rooms),
                    "stale": value.stale,
                    "unregistered_sources": value.unregistered_sources,
                }
                for value in self.observations
            ],
            "intents": [
                {
                    "observed_at": value.observed_at,
                    "category": value.category,
                    "room_id": value.room_id,
                    "action": value.action,
                }
                for value in self.intents
            ],
        }

    def _counts(self) -> dict[str, int]:
        return {
            "matched": sum(len(value.matched_rooms) for value in self.observations),
            "missing": sum(
                len(value.missing_rooms) for value in self.observations
            ),
            "moved": sum(len(value.moved_rooms) for value in self.observations),
            "stale": sum(value.stale for value in self.observations),
            "rejected": sum(
                value.category == "rejected" for value in self.intents
            ),
            "translated": sum(
                value.category == "translated" for value in self.intents
            ),
        }

    def _candidate_payload(
        self,
        *,
        registry: ClimateRegistry,
        snapshot: ClimateImportSnapshot | None,
        bridge_mode: ClimateBridgeMode,
        room_id: str | None,
    ) -> dict[str, object] | None:
        if room_id is None:
            return None
        _validate_room_id(room_id)
        matched_count = sum(
            room_id in value.matched_rooms and not value.stale
            for value in self.observations
        )
        translated_actions = {
            value.action
            for value in self.intents
            if value.category == "translated" and value.room_id == room_id
        }
        anomaly_count = sum(
            room_id in value.missing_rooms
            or room_id in value.moved_rooms
            or value.stale
            for value in self.observations
        ) + sum(
            value.category == "rejected" and value.room_id == room_id
            for value in self.intents
        )

        reasons: list[str] = []
        room = registry.room(room_id)
        if bridge_mode is ClimateBridgeMode.DISABLED:
            reasons.append("bridge_disabled")
        if room is None:
            reasons.append("candidate_not_registered")
        if snapshot is None:
            reasons.append("climate_state_unavailable")
        elif not snapshot.runtime_fresh:
            reasons.append("state_stale")
        else:
            reconciliation = reconcile_climate_registry(registry, snapshot)
            if (
                reconciliation.missing_device_ids
                or reconciliation.room_mismatch_device_ids
            ):
                reasons.append("registry_mismatch")
            imported_room = snapshot.room(room_id)
            if imported_room is None or not imported_room.authority_eligible:
                reasons.append("authority_not_ready")
            if room is not None and not _required_actions_supported(
                registry,
                snapshot,
                room_id,
            ):
                reasons.append("required_actions_unsupported")
        if matched_count < SHADOW_EVIDENCE_MIN_MATCHED_OBSERVATIONS:
            reasons.append("insufficient_matching_observations")
        if not set(SHADOW_EVIDENCE_REQUIRED_ACTIONS).issubset(translated_actions):
            reasons.append("required_shadow_intents_missing")
        if anomaly_count:
            reasons.append("shadow_anomalies_observed")

        structural_reasons = {
            "bridge_disabled",
            "candidate_not_registered",
            "climate_state_unavailable",
            "state_stale",
            "registry_mismatch",
            "authority_not_ready",
            "required_actions_unsupported",
            "shadow_anomalies_observed",
        }
        ready = not reasons
        return {
            "room_id": room_id,
            "status": (
                "ready"
                if ready
                else "blocked"
                if structural_reasons.intersection(reasons)
                else "collecting"
            ),
            "ready": ready,
            "matched_observation_count": matched_count,
            "required_matched_observation_count": (
                SHADOW_EVIDENCE_MIN_MATCHED_OBSERVATIONS
            ),
            "translated_action_count": len(
                set(SHADOW_EVIDENCE_REQUIRED_ACTIONS).intersection(
                    translated_actions
                )
            ),
            "required_actions": list(SHADOW_EVIDENCE_REQUIRED_ACTIONS),
            "anomaly_count": anomaly_count,
            "reasons": reasons,
        }


def evidence_from_storage_payload(payload: object) -> ClimateShadowEvidence:
    """Validate the exact Store representation without permissive coercion."""

    root = _exact_mapping(
        payload,
        {
            "version",
            "registry_fingerprint",
            "window_started_at",
            "observations",
            "intents",
        },
        "shadow evidence",
    )
    if root["version"] != SHADOW_EVIDENCE_STORAGE_VERSION:
        raise ClimateEvidenceViolation("shadow evidence version is unsupported")
    observations = _bounded_list(
        root["observations"],
        "shadow observations",
        SHADOW_EVIDENCE_MAX_OBSERVATIONS,
    )
    intents = _bounded_list(
        root["intents"],
        "shadow intents",
        SHADOW_EVIDENCE_MAX_INTENTS,
    )
    return ClimateShadowEvidence(
        registry_fingerprint=root["registry_fingerprint"],  # type: ignore[arg-type]
        window_started_at=root["window_started_at"],  # type: ignore[arg-type]
        observations=tuple(_observation(value) for value in observations),
        intents=tuple(_intent(value) for value in intents),
    )


def candidate_room_from_payload(payload: object) -> str:
    """Parse the exact administrator candidate query shape."""

    value = _exact_mapping(payload, {"room_id"}, "shadow candidate")["room_id"]
    if not isinstance(value, str):
        raise ClimateEvidenceViolation("shadow candidate room is invalid")
    _validate_room_id(value)
    return value


def public_intent_context(
    intent: Mapping[str, Any],
    registry: ClimateRegistry,
) -> tuple[str | None, str | None]:
    """Extract only approved public room/action labels for a rejected intent."""

    action = intent.get("action")
    safe_action = action if isinstance(action, str) and action in _APPROVED_ACTIONS else None
    room_id = intent.get("room_id")
    if isinstance(room_id, str) and registry.room(room_id) is not None:
        return room_id, safe_action
    device_id = intent.get("device_id")
    device = registry.device(device_id) if isinstance(device_id, str) else None
    return (None if device is None else device.room_id), safe_action


def _required_actions_supported(
    registry: ClimateRegistry,
    snapshot: ClimateImportSnapshot,
    room_id: str,
) -> bool:
    for intent in (
        {
            "action": "set_room_target",
            "room_id": room_id,
            "target_temperature": 24.0,
        },
        {"action": "turn_room_off", "room_id": room_id},
    ):
        try:
            plan_climate_command(
                intent,
                registry,
                snapshot,
                bridge_mode=ClimateBridgeMode.SHADOW,
            )
        except ClimateCommandViolation:
            return False
    return True


def _registry_fingerprint(registry: ClimateRegistry) -> str:
    encoded = json.dumps(
        registry_to_payload(registry),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _observation(value: object) -> ShadowObservation:
    item = _exact_mapping(
        value,
        {
            "observed_at",
            "matched_rooms",
            "missing_rooms",
            "moved_rooms",
            "stale",
            "unregistered_sources",
        },
        "shadow observation",
    )
    observed_at = _safe_timestamp(item["observed_at"], "observation timestamp")
    if type(item["stale"]) is not bool or type(item["unregistered_sources"]) is not bool:
        raise ClimateEvidenceViolation("observation flags must be boolean")
    room_sets = [
        _room_ids(item[key], key)
        for key in ("matched_rooms", "missing_rooms", "moved_rooms")
    ]
    if (
        set(room_sets[0]) & set(room_sets[1])
        or set(room_sets[0]) & set(room_sets[2])
        or set(room_sets[1]) & set(room_sets[2])
    ):
        raise ClimateEvidenceViolation("observation room categories overlap")
    return ShadowObservation(
        observed_at=observed_at,
        matched_rooms=room_sets[0],
        missing_rooms=room_sets[1],
        moved_rooms=room_sets[2],
        stale=item["stale"],  # type: ignore[arg-type]
        unregistered_sources=item["unregistered_sources"],  # type: ignore[arg-type]
    )


def _intent(value: object) -> ShadowIntent:
    item = _exact_mapping(
        value,
        {"observed_at", "category", "room_id", "action"},
        "shadow intent",
    )
    category = item["category"]
    if category not in _INTENT_CATEGORIES:
        raise ClimateEvidenceViolation("shadow intent category is invalid")
    room_id = item["room_id"]
    if room_id is not None:
        if not isinstance(room_id, str):
            raise ClimateEvidenceViolation("shadow intent room is invalid")
        _validate_room_id(room_id)
    action = item["action"]
    if action is not None and action not in _APPROVED_ACTIONS:
        raise ClimateEvidenceViolation("shadow intent action is invalid")
    return ShadowIntent(
        observed_at=_safe_timestamp(item["observed_at"], "intent timestamp"),
        category=category,  # type: ignore[arg-type]
        room_id=room_id,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
    )


def _room_ids(value: object, label: str) -> tuple[str, ...]:
    items = _bounded_list(value, label, 128)
    if any(not isinstance(item, str) for item in items):
        raise ClimateEvidenceViolation(f"{label} contains an invalid room")
    result = tuple(items)  # type: ignore[arg-type]
    for room_id in result:
        _validate_room_id(room_id)
    if result != tuple(sorted(set(result))):
        raise ClimateEvidenceViolation(f"{label} must be sorted and unique")
    return result


def _validate_room_id(value: str) -> None:
    try:
        ClimateRoom(value, "Temporary")
    except Exception as error:
        raise ClimateEvidenceViolation("shadow candidate room is invalid") from error


def _safe_timestamp(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ClimateEvidenceViolation(f"{label} must be a non-negative integer")
    return value


def _exact_mapping(
    value: object,
    keys: set[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ClimateEvidenceViolation(f"{label} must be an object")
    if set(value) != keys:
        raise ClimateEvidenceViolation(f"{label} must contain only its fixed fields")
    return value


def _bounded_list(value: object, label: str, maximum: int) -> list[object]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ClimateEvidenceViolation(f"{label} must be a bounded list")
    return value
