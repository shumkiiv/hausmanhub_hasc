"""Describe decision comparison with the working module without commands.

The comparison states only whether the already observed state of the current
climate module agrees with the strict command-free HausmanHub plan.  It uses
stable HausmanHub identifiers and approved codes only: no source binding,
Home Assistant entity, service, payload, or command authority can enter it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from .climate_observation import (
    ClimateDeviceActivity,
    ClimateObservationDeviceKind,
    ClimateRoomMode,
)
from .climate_policy import (
    ClimateFinalDeviceAction,
    ClimatePolicyAction,
    ClimateRoomPolicy,
)
from .contours import ContourMode


CLIMATE_COMPARISON_MODEL_VERSION = 1
_STABLE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ClimateComparisonViolation(ValueError):
    """A comparison result is mutable, mixed, forged, or contradictory."""


class ClimateComparisonStatus(StrEnum):
    """Whether one compared element agrees with the observed module."""

    ALIGNED = "aligned"
    DIVERGED = "diverged"
    NOT_COMPARABLE = "not_comparable"


class ClimateComparisonReason(StrEnum):
    """Bounded explanation of one divergence or comparison limit."""

    OBSERVATION_STALE = "observation_stale"
    ROOM_POLICY_MISSING = "room_policy_missing"
    ROOM_DATA_UNAVAILABLE = "room_data_unavailable"
    MANUAL_OBSERVE = "manual_observe"
    PLANNED_OBSERVE = "planned_observe"
    DEVICE_UNOBSERVED = "device_unobserved"
    DEVICE_UNAVAILABLE = "device_unavailable"
    DEVICE_ACTIVITY_UNKNOWN = "device_activity_unknown"
    DEVICE_SETTING_UNOBSERVED = "device_setting_unobserved"
    DEVICE_ACTIVITY_MISMATCH = "device_activity_mismatch"
    DEVICE_SETTING_MISMATCH = "device_setting_mismatch"


_REASON_ORDER = tuple(ClimateComparisonReason)
_MISMATCH_REASONS = frozenset(
    {
        ClimateComparisonReason.DEVICE_ACTIVITY_MISMATCH,
        ClimateComparisonReason.DEVICE_SETTING_MISMATCH,
    }
)


@dataclass(frozen=True, slots=True)
class ClimateDeviceComparison:
    """One command-free comparison of a planned and observed device state."""

    device_id: str
    room_id: str
    kind: ClimateObservationDeviceKind
    status: ClimateComparisonStatus
    reasons: tuple[ClimateComparisonReason, ...]
    planned_action: ClimateFinalDeviceAction
    observed_activity: ClimateDeviceActivity

    def __post_init__(self) -> None:
        _stable_id(self.device_id, "comparison device id")
        _stable_id(self.room_id, "comparison device room id")
        if not isinstance(self.kind, ClimateObservationDeviceKind):
            raise ClimateComparisonViolation("comparison device kind must be approved")
        if not isinstance(self.planned_action, ClimateFinalDeviceAction):
            raise ClimateComparisonViolation(
                "comparison planned action must be approved"
            )
        if not isinstance(self.observed_activity, ClimateDeviceActivity):
            raise ClimateComparisonViolation(
                "comparison observed activity must be approved"
            )
        _reasons(self.status, self.reasons)


@dataclass(frozen=True, slots=True)
class ClimateRoomComparison:
    """One command-free decision comparison for a configured room."""

    room_id: str
    status: ClimateComparisonStatus
    reasons: tuple[ClimateComparisonReason, ...]
    planned_policy: ClimateRoomPolicy | None
    planned_action: ClimatePolicyAction | None
    observed_mode: ClimateRoomMode
    devices: tuple[ClimateDeviceComparison, ...]

    def __post_init__(self) -> None:
        _stable_id(self.room_id, "comparison room id")
        _reasons(self.status, self.reasons)
        if self.planned_policy is not None and not isinstance(
            self.planned_policy,
            ClimateRoomPolicy,
        ):
            raise ClimateComparisonViolation(
                "comparison planned policy must be approved"
            )
        if self.planned_action is not None and not isinstance(
            self.planned_action,
            ClimatePolicyAction,
        ):
            raise ClimateComparisonViolation(
                "comparison planned room action must be approved"
            )
        if (self.planned_policy is None) != (self.planned_action is None):
            raise ClimateComparisonViolation(
                "planned policy and action must appear together"
            )
        if not isinstance(self.observed_mode, ClimateRoomMode):
            raise ClimateComparisonViolation(
                "comparison observed room mode must be approved"
            )
        if type(self.devices) is not tuple or any(
            not isinstance(device, ClimateDeviceComparison) for device in self.devices
        ):
            raise ClimateComparisonViolation(
                "comparison devices must be an immutable typed tuple"
            )
        if len(self.devices) != len({device.device_id for device in self.devices}):
            raise ClimateComparisonViolation("comparison device ids must be unique")
        if any(device.room_id != self.room_id for device in self.devices):
            raise ClimateComparisonViolation(
                "comparison devices must belong to their room"
            )
        if self.status is ClimateComparisonStatus.ALIGNED and any(
            device.status is not ClimateComparisonStatus.ALIGNED
            for device in self.devices
        ):
            raise ClimateComparisonViolation(
                "aligned room cannot retain unaligned devices"
            )
        device_mismatch = any(
            device.status is ClimateComparisonStatus.DIVERGED for device in self.devices
        )
        if self.status is ClimateComparisonStatus.DIVERGED and not device_mismatch:
            raise ClimateComparisonViolation(
                "diverged room requires one diverged device"
            )


@dataclass(frozen=True, slots=True)
class ClimateComparisonSnapshot:
    """Complete command-free decision comparison for one observation."""

    contour_id: str
    contour_mode: ContourMode
    observed_at: int
    rooms: tuple[ClimateRoomComparison, ...]
    version: int = CLIMATE_COMPARISON_MODEL_VERSION

    def __post_init__(self) -> None:
        _stable_id(self.contour_id, "comparison contour id")
        if not isinstance(self.contour_mode, ContourMode):
            raise ClimateComparisonViolation(
                "comparison contour mode must be approved"
            )
        if type(self.observed_at) is not int or self.observed_at < 0:
            raise ClimateComparisonViolation(
                "comparison observation time must be a non-negative integer"
            )
        if type(self.rooms) is not tuple or any(
            not isinstance(room, ClimateRoomComparison) for room in self.rooms
        ):
            raise ClimateComparisonViolation(
                "comparison rooms must be an immutable typed tuple"
            )
        if not self.rooms:
            raise ClimateComparisonViolation("comparison rooms must not be empty")
        if len(self.rooms) != len({room.room_id for room in self.rooms}):
            raise ClimateComparisonViolation("comparison room ids must be unique")
        if (
            type(self.version) is not int
            or self.version != CLIMATE_COMPARISON_MODEL_VERSION
        ):
            raise ClimateComparisonViolation(
                "climate comparison model version is unsupported"
            )

    @property
    def commands_enabled(self) -> bool:
        """Decision comparison can never authorize a physical command."""

        return False

    @property
    def aligned_room_count(self) -> int:
        """Return how many rooms fully agree with the observed module."""

        return sum(
            room.status is ClimateComparisonStatus.ALIGNED for room in self.rooms
        )

    @property
    def diverged_room_ids(self) -> tuple[str, ...]:
        """Return only rooms with at least one confirmed mismatch."""

        return tuple(
            room.room_id
            for room in self.rooms
            if room.status is ClimateComparisonStatus.DIVERGED
        )

    @property
    def not_comparable_room_ids(self) -> tuple[str, ...]:
        """Return only rooms that cannot be compared honestly right now."""

        return tuple(
            room.room_id
            for room in self.rooms
            if room.status is ClimateComparisonStatus.NOT_COMPARABLE
        )

    def room(self, room_id: str) -> ClimateRoomComparison | None:
        """Return one compared room by stable HausmanHub id."""

        return next((room for room in self.rooms if room.room_id == room_id), None)


def _stable_id(value: object, label: str) -> None:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ClimateComparisonViolation(f"{label} must be a stable HausmanHub id")


def _reasons(
    status: object,
    reasons: object,
) -> None:
    if not isinstance(status, ClimateComparisonStatus):
        raise ClimateComparisonViolation("comparison status must be approved")
    if type(reasons) is not tuple or any(
        not isinstance(reason, ClimateComparisonReason) for reason in reasons
    ):
        raise ClimateComparisonViolation(
            "comparison reasons must be immutable and typed"
        )
    if len(reasons) != len(set(reasons)):
        raise ClimateComparisonViolation("comparison reasons must be unique")
    if reasons != tuple(reason for reason in _REASON_ORDER if reason in reasons):
        raise ClimateComparisonViolation("comparison reasons must use the fixed order")
    has_mismatch = bool(set(reasons).intersection(_MISMATCH_REASONS))
    if status is ClimateComparisonStatus.ALIGNED and reasons:
        raise ClimateComparisonViolation("aligned result cannot retain reasons")
    if status is ClimateComparisonStatus.DIVERGED and not has_mismatch:
        raise ClimateComparisonViolation("diverged result requires a mismatch")
    if status is ClimateComparisonStatus.NOT_COMPARABLE and (
        not reasons or has_mismatch
    ):
        raise ClimateComparisonViolation(
            "not-comparable result requires only comparison limits"
        )
