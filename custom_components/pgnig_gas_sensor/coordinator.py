"""One poll of the Orlen EBOK API, shared by every entity of a config entry."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth.exceptions import AuthError
from .const import DATA_UPDATE_INTERVAL_HOURS, DOMAIN
from .Invoices import InvoicesList
from .PgnigApi import PgnigApi
from .PgpList import PpgList
from .PpgReadingForMeter import MeterReading

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=DATA_UPDATE_INTERVAL_HOURS)


def latest_reading(readings: Sequence[MeterReading] | None) -> MeterReading | None:
    """The most recent reading, or None when the meter has never reported one."""
    if not readings:
        return None
    return max(readings, key=lambda reading: reading.reading_date_utc)


@dataclass(frozen=True)
class PgnigData:
    """Everything the entities of a config entry need, from a single poll."""

    readings: Mapping[str, MeterReading | None]
    invoices: tuple[InvoicesList, ...]


class PgnigCoordinator(DataUpdateCoordinator[PgnigData]):
    """Fetches every meter reading and the invoice list once per interval.

    Entities used to call the API from their own async_update. That fetched the
    invoice list twice per meter, and it hid authentication failures: Home
    Assistant catches whatever an entity update raises, so an expired session
    only ever became a log entry. ConfigEntryAuthFailed raised here makes HA
    start the reauth flow, which is what actually asks the user to log in.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry | None,
        api: PgnigApi,
        meters: PpgList,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.meters = meters

    async def _async_update_data(self) -> PgnigData:
        return await self.hass.async_add_executor_job(self._fetch)

    def _fetch(self) -> PgnigData:
        """Poll every meter plus the shared invoice list, in one executor job."""
        try:
            readings = {
                meter.meter_number: latest_reading(
                    self.api.readingForMeter(meter.meter_number).meter_readings
                )
                for meter in self.meters.ppg_list
            }
            invoices = tuple(self.api.invoices().invoices_list)
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Could not refresh Orlen EBOK data: {err}") from err

        return PgnigData(readings=readings, invoices=invoices)
