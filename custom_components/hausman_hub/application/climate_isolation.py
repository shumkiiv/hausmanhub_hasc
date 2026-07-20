"""Calculate each climate room independently and fail closed per room."""

from __future__ import annotations

from dataclasses import replace

from ..domain.climate_demand import ClimateDemandViolation
from ..domain.climate_equipment import ClimateEquipmentViolation
from ..domain.climate_isolation import (
    ClimateIsolatedRoomResult,
    ClimateIsolationReason,
    ClimateIsolationSnapshot,
    ClimateRoomIsolationStatus,
)
from ..domain.climate_observation import (
    ClimateDataStatus,
    ClimateDeviceAvailability,
    ClimateObservationSnapshot,
)
from ..domain.climate_policy import ClimatePolicyViolation, ClimateRoomPolicyPlan
from ..domain.climate_resolution import ClimateResolutionViolation
from ..domain.climate_stability import ClimateStabilityViolation
from ..domain.climate_targets import ClimateTargetViolation
from ..domain.contours import (
    ClimateContourRoom,
    ContourDefinition,
    ContourKind,
    ContourViolation,
)
from .climate_demands import build_climate_demand_snapshot
from .climate_equipment import build_climate_equipment_snapshot
from .climate_policy import build_climate_policy_snapshot
from .climate_resolutions import build_climate_resolution_snapshot
from .climate_stability import build_climate_stability_snapshot
from .climate_targets import build_climate_target_snapshot


_ROOM_CALCULATION_FAILURES = (
    ContourViolation,
    ClimateTargetViolation,
    ClimateDemandViolation,
    ClimateResolutionViolation,
    ClimateEquipmentViolation,
    ClimateStabilityViolation,
    ClimatePolicyViolation,
)


def build_isolated_climate_policy_snapshot(
    contour: ContourDefinition,
    observation: ClimateObservationSnapshot,
) -> ClimateIsolationSnapshot:
    """Keep valid room and device plans when a neighbour's inputs fail."""

    if (
        not isinstance(contour, ContourDefinition)
        or contour.kind is not ContourKind.CLIMATE
    ):
        raise ClimatePolicyViolation("a validated climate contour is required")
    if not isinstance(observation, ClimateObservationSnapshot):
        raise ClimatePolicyViolation("a validated climate observation is required")

    rooms = tuple(
        _build_isolated_room_result(contour, contour_room, observation)
        for contour_room in contour.rooms
    )
    return ClimateIsolationSnapshot(
        contour_id=contour.contour_id,
        contour_mode=contour.mode,
        observed_at=observation.observed_at,
        rooms=rooms,
    )


def _build_isolated_room_result(
    contour: ContourDefinition,
    contour_room: ClimateContourRoom,
    observation: ClimateObservationSnapshot,
) -> ClimateIsolatedRoomResult:
    observed_room = observation.room(contour_room.room_id)
    if observed_room is None:
        return ClimateIsolatedRoomResult(
            room_id=contour_room.room_id,
            status=ClimateRoomIsolationStatus.FAILED,
            reasons=(ClimateIsolationReason.ROOM_INPUT_MISSING,),
            failed_device_ids=(),
            policy=None,
        )

    selected = tuple(
        observation.device(device_id) for device_id in contour_room.device_ids
    )
    missing_device_ids = tuple(
        device_id
        for device_id, device in zip(contour_room.device_ids, selected, strict=True)
        if device is None or device.room_id != contour_room.room_id
    )
    retained_device_ids = tuple(
        device.device_id
        for device in selected
        if device is not None and device.room_id == contour_room.room_id
    )
    if not retained_device_ids:
        return ClimateIsolatedRoomResult(
            room_id=contour_room.room_id,
            status=ClimateRoomIsolationStatus.FAILED,
            reasons=(
                ClimateIsolationReason.DEVICE_INPUT_MISSING,
                ClimateIsolationReason.NO_USABLE_DEVICES,
            ),
            failed_device_ids=missing_device_ids or contour_room.device_ids,
            policy=None,
        )

    isolated_room = replace(contour_room, device_ids=retained_device_ids)
    isolated_contour = replace(contour, rooms=(isolated_room,))
    try:
        policy = _build_isolated_room_policy(isolated_contour, observation)
    except _ROOM_CALCULATION_FAILURES:
        reasons = (
            (ClimateIsolationReason.DEVICE_INPUT_MISSING,)
            if missing_device_ids
            else ()
        ) + (ClimateIsolationReason.CALCULATION_FAILED,)
        return ClimateIsolatedRoomResult(
            room_id=contour_room.room_id,
            status=ClimateRoomIsolationStatus.FAILED,
            reasons=reasons,
            failed_device_ids=missing_device_ids,
            policy=None,
        )

    reasons: list[ClimateIsolationReason] = []
    failed_device_ids = list(missing_device_ids)
    if observed_room.data_status is ClimateDataStatus.STALE:
        reasons.append(ClimateIsolationReason.ROOM_DATA_STALE)
    elif observed_room.data_status is ClimateDataStatus.UNAVAILABLE:
        reasons.append(ClimateIsolationReason.ROOM_DATA_UNAVAILABLE)
    if missing_device_ids:
        reasons.append(ClimateIsolationReason.DEVICE_INPUT_MISSING)
    for device in selected:
        if device is None or device.room_id != contour_room.room_id:
            continue
        if device.availability is ClimateDeviceAvailability.MISSING:
            reasons.append(ClimateIsolationReason.DEVICE_MISSING)
            failed_device_ids.append(device.device_id)
        elif device.availability is ClimateDeviceAvailability.UNAVAILABLE:
            reasons.append(ClimateIsolationReason.DEVICE_UNAVAILABLE)
            failed_device_ids.append(device.device_id)
    ordered_reasons = tuple(
        reason for reason in ClimateIsolationReason if reason in reasons
    )
    unique_failed_device_ids = tuple(
        dict.fromkeys(failed_device_ids)
    )
    if observed_room.data_status is ClimateDataStatus.UNAVAILABLE:
        status = ClimateRoomIsolationStatus.UNAVAILABLE
    elif ordered_reasons:
        status = ClimateRoomIsolationStatus.DEGRADED
    else:
        status = ClimateRoomIsolationStatus.READY
    return ClimateIsolatedRoomResult(
        room_id=contour_room.room_id,
        status=status,
        reasons=ordered_reasons,
        failed_device_ids=unique_failed_device_ids,
        policy=policy,
    )


def _build_isolated_room_policy(
    contour: ContourDefinition,
    observation: ClimateObservationSnapshot,
) -> ClimateRoomPolicyPlan:
    """Run the existing strict pipeline for exactly one retained room."""

    targets = build_climate_target_snapshot(contour, observation)
    demands = build_climate_demand_snapshot(targets, observation)
    resolutions = build_climate_resolution_snapshot(demands, observation)
    equipment = build_climate_equipment_snapshot(
        contour,
        targets,
        resolutions,
        observation,
    )
    stability = build_climate_stability_snapshot(
        contour,
        targets,
        equipment,
        observation,
    )
    snapshot = build_climate_policy_snapshot(
        contour,
        resolutions,
        equipment,
        stability,
        observation,
    )
    return snapshot.rooms[0]
