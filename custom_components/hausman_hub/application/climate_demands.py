"""Build command-free climate demand from targets and observations."""

from __future__ import annotations

from ..domain.climate_demand import (
    ClimateDemandSnapshot,
    ClimateDemandViolation,
    ClimateRoomDemand,
    resolve_climate_room_demand,
)
from ..domain.climate_observation import ClimateObservationSnapshot
from ..domain.climate_targets import ClimateTargetSnapshot
from .climate_observations import climate_reference_observation
from .climate_targets import climate_reference_target


def build_climate_demand_snapshot(
    targets: ClimateTargetSnapshot,
    observation: ClimateObservationSnapshot,
) -> ClimateDemandSnapshot:
    """Calculate independent needs for every configured contour room."""

    if not isinstance(targets, ClimateTargetSnapshot):
        raise ClimateDemandViolation("a validated climate target snapshot is required")
    if not isinstance(observation, ClimateObservationSnapshot):
        raise ClimateDemandViolation(
            "a validated climate observation snapshot is required"
        )
    observation_room_ids = {room.room_id for room in observation.rooms}
    target_room_ids = {room.room_id for room in targets.rooms}
    if not target_room_ids.issubset(observation_room_ids):
        raise ClimateDemandViolation(
            "every climate target room requires an observation placeholder"
        )
    rooms = tuple(
        resolve_climate_room_demand(
            target,
            observation.room(target.room_id),
        )
        for target in targets.rooms
    )
    return ClimateDemandSnapshot(
        contour_id=targets.contour_id,
        contour_mode=targets.contour_mode,
        rooms=rooms,
    )


def climate_reference_demand(case_id: str) -> ClimateRoomDemand:
    """Calculate raw room demand for one frozen migration case."""

    observation = climate_reference_observation(case_id)
    target = climate_reference_target(case_id)
    return resolve_climate_room_demand(target, observation.rooms[0])
