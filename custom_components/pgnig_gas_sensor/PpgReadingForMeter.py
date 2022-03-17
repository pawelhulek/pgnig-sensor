from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, TypeVar, Callable, Type, cast
import dateutil.parser

T = TypeVar("T")


def from_str(x: Any) -> str:
    assert isinstance(x, str)
    return x


def from_datetime(x: Any) -> datetime:
    return dateutil.parser.parse(x)


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_none(x: Any) -> Any:
    assert x is None
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


@dataclass
class MeterReading:
    status: str
    reading_date_local: datetime
    reading_date_utc: datetime
    pp_id: int
    value: int
    value2: None
    value3: None
    meter_number: str
    region_code: str
    wear: int
    type: str
    color: str

    @staticmethod
    def from_dict(obj: Any) -> 'MeterReading':
        assert isinstance(obj, dict)
        status = from_str(obj.get("Status"))
        reading_date_local = from_datetime(obj.get("ReadingDateLocal"))
        reading_date_utc = from_datetime(obj.get("ReadingDateUtc"))
        pp_id = int(from_str(obj.get("PpId")))
        value = from_int(obj.get("Value"))
        value2 = from_none(obj.get("Value2"))
        value3 = from_none(obj.get("Value3"))
        meter_number = from_str(obj.get("MeterNumber"))
        region_code = from_str(obj.get("RegionCode"))
        wear = from_int(obj.get("Wear"))
        type = from_str(obj.get("Type"))
        color = from_str(obj.get("Color"))
        return MeterReading(status, reading_date_local, reading_date_utc, pp_id, value, value2, value3, meter_number,
                            region_code, wear, type, color)

    def to_dict(self) -> dict:
        result: dict = {"Status": from_str(self.status), "ReadingDateLocal": self.reading_date_local.isoformat(),
                        "ReadingDateUtc": self.reading_date_utc.isoformat(), "PpId": from_str(str(self.pp_id)),
                        "Value": from_int(self.value), "Value2": from_none(self.value2),
                        "Value3": from_none(self.value3), "MeterNumber": from_str(self.meter_number),
                        "RegionCode": from_str(self.region_code), "Wear": from_int(self.wear),
                        "Type": from_str(self.type), "Color": from_str(self.color)}
        return result


@dataclass
class PpgReadingForMeter:
    meter_readings: List[MeterReading]
    code: int
    message: None
    display_to_end_user: bool
    end_user_message: None
    token_expire_date: datetime
    token_expire_date_utc: datetime

    @staticmethod
    def from_dict(obj: Any) -> 'PpgReadingForMeter':
        assert isinstance(obj, dict)
        meter_readings = from_list(MeterReading.from_dict, obj.get("MeterReadings"))
        code = from_int(obj.get("Code"))
        message = from_none(obj.get("Message"))
        display_to_end_user = from_bool(obj.get("DisplayToEndUser"))
        end_user_message = from_none(obj.get("EndUserMessage"))
        token_expire_date = from_datetime(obj.get("TokenExpireDate"))
        token_expire_date_utc = from_datetime(obj.get("TokenExpireDateUtc"))
        return PpgReadingForMeter(meter_readings, code, message, display_to_end_user, end_user_message,
                                  token_expire_date, token_expire_date_utc)

    def to_dict(self) -> dict:
        result: dict = {"MeterReadings": from_list(lambda x: to_class(MeterReading, x), self.meter_readings),
                        "Code": from_int(self.code), "Message": from_none(self.message),
                        "DisplayToEndUser": from_bool(self.display_to_end_user),
                        "EndUserMessage": from_none(self.end_user_message),
                        "TokenExpireDate": self.token_expire_date.isoformat(),
                        "TokenExpireDateUtc": self.token_expire_date_utc.isoformat()}
        return result


def ppg_reading_for_meter_from_dict(s: Any) -> PpgReadingForMeter:
    return PpgReadingForMeter.from_dict(s)


def ppg_reading_for_meter_to_dict(x: PpgReadingForMeter) -> Any:
    return to_class(PpgReadingForMeter, x)
