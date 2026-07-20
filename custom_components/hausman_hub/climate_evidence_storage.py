"""Versioned Home Assistant Store adapter for redacted climate evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from .application.climate_evidence import (
    ClimateEvidenceViolation,
    ClimateShadowEvidence,
    SHADOW_EVIDENCE_STORAGE_VERSION,
    evidence_from_storage_payload,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ClimateEvidenceStorageError(RuntimeError):
    """Persisted climate shadow evidence is damaged or unavailable."""


class HomeAssistantClimateEvidenceStore:
    """Persist one bounded evidence window per single HausmanHub config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = Store(
            hass,
            SHADOW_EVIDENCE_STORAGE_VERSION,
            f"hausman_hub.climate_shadow_evidence.{entry_id}",
        )

    async def async_load(self) -> ClimateShadowEvidence | None:
        """Return no evidence only when no window has ever been saved."""

        payload = await self._store.async_load()
        if payload is None:
            return None
        try:
            return evidence_from_storage_payload(payload)
        except ClimateEvidenceViolation as error:
            raise ClimateEvidenceStorageError(
                "stored climate shadow evidence is invalid"
            ) from error

    async def async_save(self, evidence: ClimateShadowEvidence) -> None:
        """Save only the exact validated bounded evidence shape."""

        await self._store.async_save(evidence.as_storage_payload())
