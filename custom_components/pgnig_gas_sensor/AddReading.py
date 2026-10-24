"""Payload and result types for submitting a meter reading to Orlen EBOK."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# Result codes returned by /crm/add-ppg-reading-v2 (0 means accepted).
READING_ERROR_MESSAGES: dict[int, str] = {
    1: "Orlen rejected the value as invalid",
    1031: "Orlen rejected the value as invalid",
    1032: "A reading for this period has already been submitted",
    1040: (
        "Orlen wants confirmation that the meter was replaced or rolled over "
        "(the value is lower than the previous reading). Repeat the call with "
        "consent_meter_reset: true if that is correct."
    ),
    1072: "Orlen requires an extra confirmation for this reading that must be given on the website",
}


@dataclass(frozen=True)
class ReadingSubmission:
    """A meter reading to send to Orlen EBOK."""

    meter_id: str
    value: float
    reading_date: date
    consent_meter_reset: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "DateReading": self.reading_date.isoformat(),
            "OsdNumber": self.meter_id,
            "Value": self.value,
            "ConsentMeterReset": self.consent_meter_reset,
            "UseDate": True,
            "SourceFromWWW": True,
        }


@dataclass(frozen=True)
class ReadingResult:
    """Accepted reading, as echoed back by Orlen EBOK."""

    meter_id: str
    value: float | None
    added_at_utc: str | None
    can_be_cancelled: bool

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ReadingResult":
        reading = data.get("Reading") or {}
        return ReadingResult(
            meter_id=reading.get("MeterNumber", ""),
            value=reading.get("Value"),
            added_at_utc=reading.get("ReadingDateAddedUtc"),
            can_be_cancelled=bool(reading.get("CanBeCancelled", False)),
        )


def error_message(code: int) -> str:
    return READING_ERROR_MESSAGES.get(
        code, f"Orlen EBOK rejected the reading with code {code}"
    )
