"""Diagnostics support for PGNIG Gas Sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD
from .PgnigApi import PgnigApi
from .Invoices import InvoicesList
from .PpgReadingForMeter import MeterReading

_LOGGER = logging.getLogger(__name__)

TO_REDACT = {"username", "password"}


async def async_get_config_entry_diagnostics(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    username = config_entry.data.get("username")
    password = config_entry.data.get("password")
    auth_method = config_entry.data.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)

    api = PgnigApi(username, password, auth_method)

    meters = await hass.async_add_executor_job(api.meterList)
    invoices = await hass.async_add_executor_job(api.invoices)

    readings = []
    for meter in meters.ppg_list:
        meter_readings = await hass.async_add_executor_job(api.readingForMeter, meter.meter_number)
        latest = max(meter_readings.meter_readings, key=lambda x: x.reading_date_utc) if meter_readings.meter_readings else None
        readings.append({
            "meter_id": meter.meter_number,
            "id_local": meter.id_local,
            "latest_reading": {
                "value": latest.value if latest else None,
                "date": str(latest.reading_date_utc) if latest else None,
                "wear": latest.wear if latest else None,
            } if latest else None,
        })

    data = {
        "config_entry": async_redact_data(config_entry.data, TO_REDACT),
        "meters": [
            {"meter_number": m.meter_number, "id_local": m.id_local}
            for m in meters.ppg_list
        ],
        "meter_readings": readings,
        "invoices_count": len(invoices.invoices_list),
        "unpaid_invoices": [
            {
                "id": inv.number,
                "amount": inv.amount_to_pay,
                "date": str(inv.date),
                "is_paid": inv.is_paid,
            }
            for inv in invoices.invoices_list
            if not inv.is_paid and str(inv.id_pp) in [str(m.id_local) for m in meters.ppg_list]
        ],
    }

    return data
