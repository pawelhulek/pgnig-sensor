from datetime import datetime

from pgnig_gas_sensor.PpgReadingForMeter import MeterReading, PpgReadingForMeter
from pytest_homeassistant_custom_component.async_mock import AsyncMock, MagicMock

from custom_components.pgnig_gas_sensor.sensor import PgnigSensor


async def test_newer_takes_precedence(hass):
    # given
    pgnig_api = MagicMock()
    reading_newer = anyMeterReading()
    reading_newer.reading_date_utc = datetime(2022, 7, 5)
    reading_newer.value = 2

    reading_older = anyMeterReading()
    reading_older.reading_date_utc = datetime(2022, 7, 4)
    reading_older.value = 3
    pgnig_api.readingForMeter = MagicMock(return_value=(
        PpgReadingForMeter(meter_readings=[reading_older, reading_newer], code=0, message=None,
                           display_to_end_user=None,
                           token_expire_date=None,
                           token_expire_date_utc=None, end_user_message=None)))
    sensor = PgnigSensor(hass, pgnig_api, "1", 2)
    # when
    await sensor.async_update()
    # then
    assert sensor._state.value == 2


def anyMeterReading():
    return MeterReading(status="",
                        reading_date_local=datetime(2022, 6, 6),
                        reading_date_utc=datetime(2022, 6, 6),
                        pp_id=None,
                        value=2,
                        value2=None,
                        value3=None,
                        meter_number=None,
                        region_code=None,
                        wear=None,
                        type=None,
                        color=None)
