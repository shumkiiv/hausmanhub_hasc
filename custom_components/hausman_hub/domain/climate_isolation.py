"""Describe fault-isolated climate results without creating commands.

One invalid room input must not erase valid plans for the remaining rooms.
This model keeps that boundary explicit and exposes only stable HausmanHub
identifiers plus already validated room policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from .climate_policy import ClimateRoomPolicyPlan
from .contours import ContourMode


CLIMATE_ISOLATION_MODEL_VERSION = 1
_STABLE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ClimateIsolationViolation(ValueError):
    """A fault-isolation result is mutable, mixed, or contradictory."""


class ClimateRoomIsolationStatus(StrEnum):
    """Whether one room retained a safe policy after isolated calculation."""

    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class ClimateIsolationReason(StrEnum):
    """Bounded reason why one room is not fully ready."""

    ROOM_INPUT_MISSING = "room_input_missing"
    ROOM_DATA_STALE = "room_data_stale"
    ROOM_DATA_UNAVAILABLE = "room_data_unavailable"
    DEVICE_INPUT_MISSING = "device_input_missing"
    DEVICE_MISSING = "device_missing"
    DEVICE_UNAVAILABLE = "device_unavailable"
    NO_USABLE_DEVICES = "no_usable_devices"
    CALCULATION_FAILED = "calculation_failed"


_REASON_ORDER = tuple(ClimateIsolationReason)
_FAILED_REASONS = frozenset(
    {
        ClimateIsolationReason.ROOM_INPUT_MISSING,
        ClimateIsolationReason.DEVICE_INPUT_MISSING,
        ClimateIsolationReason.NO_USABLE_DEVICES,
        ClimateIsolationReason.CALCULATION_FAILED,
    }
)
_DEVICE_REASONS = frozenset(
    {
        ClimateIsolationReason.DEVICE_INPUT_MISSING,
        ClimateIsolationReason.DEVICE_MISSING,
        ClimateIsolationReason.DEVICE_UNAVAILABLE,
        ClimateIsolationReason.NO_USABLE_DEVICES,
    }
)
_DEGRADED_REASONS = frozenset(
    {
        ClimateIsolationReason.ROOM_DATA_STALE,
        ClimateIsolationReason.DEVICE_INPUT_MISSING,
        ClimateIsolationReason.DEVICE_MISSING,
        ClimateIsolationReason.DEVICE_UNAVAILABLE,
    }
)
_UNAVAILABLE_REASONS = frozenset(
    {
        ClimateIsolationReason.ROOM_DATA_UNAVAILABLE,
        ClimateIsolationReason.DEVICE_INPUT_MISSING,
        ClimateIsolationReason.DEVICE_MISSING,
        ClimateIsolationReason.DEVICE_UNAVAILABLE,
    }
)


@dataclass(frozen=True, slots=True)
class ClimateIsolatedRoomResult:
    """One independently calculated room and its bounded failure summary."""

    room_id: str
    status: ClimateRoomIsolationStatus
    reasons: tuple[ClimateIsolationReason, ...]
    failed_device_ids: tuple[str, ...]
    policy: ClimateRoomPolicyPlan | None

    def __post_init__(self) -> None:
        _stable_id(self.room_id, "isolated room id")
        if not isinstance(self.status, ClimateRoomIsolationStatus):
            raise ClimateIsolationViolation("room isolation status must be approved")
        if type(self.reasons) is not tuple or any(
            not isinstance(reason, ClimateIsolationReason) for reason in self.reasons
        ):
            raise ClimateIsolationViolation(
                "room isolation reasons must be immutable and typed"
            )
        if len(self.reasons) != len(set(self.reasons)):
            raise ClimateIsolationViolation("room isolation reasons must be unique")
        if self.reasons != tuple(
            reason for reason in _REASON_ORDER if reason in self.reasons
        ):
            raise ClimateIsolationViolation(
                "room isolation reasons must use the fixed order"
            )
        if type(self.failed_device_ids) is not tuple:
            raise ClimateIsolationViolation(
                "failed device ids must be an immutable tuple"
            )
        for device_id in self.failed_device_ids:
            _stable_id(device_id, "failed device id")
        if len(self.failed_device_ids) != len(set(self.failed_device_ids)):
            raise ClimateIsolationViolation("failed device ids must be unique")
        if self.policy is not None:
            if not isinstance(self.policy, ClimateRoomPolicyPlan):
                raise ClimateIsolationViolation("isolated policy must be validated")
            if self.policy.room_id != self.room_id:
                raise ClimateIsolationViolation(
                    "isolated policy must belong to the same room"
                )

        if self.status is ClimateRoomIsolationStatus.READY:
            if self.policy is None or self.reasons or self.failed_device_ids:
                raise ClimateIsolationViolation(
                    "ready room requires one clean validated policy"
                )
        elif self.status is ClimateRoomIsolationStatus.DEGRADED:
            if (
                self.policy is None
                or not self.reasons
                or not set(self.reasons).issubset(_DEGRADED_REASONS)
            ):
                raise ClimateIsolationViolation(
                    "degraded room requires a policy and degradable reasons"
                )
        elif self.status is ClimateRoomIsolationStatus.UNAVAILABLE:
            if (
                self.policy is None
                or ClimateIsolationReason.ROOM_DATA_UNAVAILABLE not in self.reasons
                or not set(self.reasons).issubset(_UNAVAILABLE_REASONS)
            ):
                raise ClimateIsolationViolation(
                    "unavailable room requires a safe policy and room-data reason"
                )
        else:
            reason_set = set(self.reasons)
            valid_failed_shape = (
                self.policy is None
                and bool(reason_set.intersection(_FAILED_REASONS))
                and reason_set.issubset(_FAILED_REASONS)
                and (
                    reason_set == {ClimateIsolationReason.ROOM_INPUT_MISSING}
                    or ClimateIsolationReason.CALCULATION_FAILED in reason_set
                    or {
                        ClimateIsolationReason.DEVICE_INPUT_MISSING,
                        ClimateIsolationReason.NO_USABLE_DEVICES,
                    }.issubset(reason_set)
                )
            )
            if not valid_failed_shape:
                raise ClimateIsolationViolation(
                    "failed room must have no policy and bounded failure reasons"
                )

        has_device_reason = bool(set(self.reasons).intersection(_DEVICE_REASONS))
        if bool(self.failed_device_ids) != has_device_reason:
            raise ClimateIsolationViolation(
                "failed device ids and device failure reasons must agree"
            )


@dataclass(frozen=True, slots=True)
class ClimateIsolationSnapshot:
    """Complete fault-isolated result for every configured contour room."""

    contour_id: str
    contour_mode: ContourMode
    observed_at: int
    rooms: tuple[ClimateIsolatedRoomResult, ...]
    version: int = CLIMATE_ISOLATION_MODEL_VERSION

    def __post_init__(self) -> None:
        _stable_id(self.contour_id, "isolation contour id")
        if not isinstance(self.contour_mode, ContourMode):
            raise ClimateIsolationViolation("isolation contour mode must be approved")
        if type(self.observed_at) is not int or self.observed_at < 0:
            raise ClimateIsolationViolation(
                "isolation observation time must be non-negative"
            )
        if type(self.rooms) is not tuple or any(
            not isinstance(room, ClimateIsolatedRoomResult) for room in self.rooms
        ):
            raise ClimateIsolationViolation(
                "isolated rooms must be immutable and typed"
            )
        if not self.rooms:
            raise ClimateIsolationViolation("isolated rooms must not be empty")
        if len(self.rooms) != len({room.room_id for room in self.rooms}):
            raise ClimateIsolationViolation("isolated room ids must be unique")
        for room in self.rooms:
            if room.policy is not None and (
                room.policy.observed_at != self.observed_at
                or room.policy.contour_mode is not self.contour_mode
            ):
                raise ClimateIsolationViolation(
                    "isolated policies must use one contour mode and observation"
                )
        if self.version != CLIMATE_ISOLATION_MODEL_VERSION:
            raise ClimateIsolationViolation(
                "climate isolation model version is unsupported"
            )

    @property
    def commands_enabled(self) -> bool:
        """Fault isolation cannot authorize Home Assistant commands."""

        return False

    @property
    def ready_room_count(self) -> int:
        """Return how many rooms have a complete clean policy."""

        return sum(
            room.status is ClimateRoomIsolationStatus.READY for room in self.rooms
        )

    @property
    def available_policy_count(self) -> int:
        """Return how many rooms retained a validated policy."""

        return sum(room.policy is not None for room in self.rooms)

    @property
    def failed_room_ids(self) -> tuple[str, ...]:
        """Return only rooms whose calculation produced no usable policy."""

        return tuple(
            room.room_id
            for room in self.rooms
            if room.status is ClimateRoomIsolationStatus.FAILED
        )

    def room(self, room_id: str) -> ClimateIsolatedRoomResult | None:
        """Return one isolated room by stable HausmanHub id."""

        return next((room for room in self.rooms if room.room_id == room_id), None)


def _stable_id(value: object, label: str) -> None:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ClimateIsolationViolation(f"{label} must be a stable HausmanHub id")
