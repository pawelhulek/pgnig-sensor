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


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    return [f(y) for y in x]


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_none(x: Any) -> Any:
    assert x is None
    return x


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


@dataclass
class PpgListElement:
    id_ppg: str
    meter_number: str
    contract_number: str
    has_t12: bool
    reading_added: bool
    tariff: str
    has_history: bool
    type: str
    id_local: int
    client_number: int
    installation_number: str
    color: str
    agreement_name: str
    can_create_home_assistant: bool
    add_reading_mode: str
    is_in_migration: bool
    is_in_migration_rk: bool
    is_in_migration_rw: bool
    is_company: bool

    @staticmethod
    def from_dict(obj: Any) -> 'PpgListElement':
        assert isinstance(obj, dict)
        id_ppg = from_str(obj.get("IdPPG"))
        meter_number = from_str(obj.get("MeterNumber"))
        contract_number = from_str(obj.get("ContractNumber"))
        has_t12 = from_bool(obj.get("HasT12"))
        reading_added = from_bool(obj.get("ReadingAdded"))
        tariff = from_str(obj.get("Tariff"))
        has_history = from_bool(obj.get("HasHistory"))
        type = from_str(obj.get("Type"))
        id_local = int(from_str(obj.get("IdLocal")))
        client_number = int(from_str(obj.get("ClientNumber")))
        installation_number = from_str(obj.get("InstallationNumber"))
        color = from_str(obj.get("Color"))
        agreement_name = from_str(obj.get("AgreementName"))
        can_create_home_assistant = from_bool(obj.get("CanCreateHomeAssistant"))
        add_reading_mode = from_str(obj.get("AddReadingMode"))
        is_in_migration = from_bool(obj.get("IsInMigration"))
        is_in_migration_rk = from_bool(obj.get("IsInMigrationRK"))
        is_in_migration_rw = from_bool(obj.get("IsInMigrationRW"))
        is_company = from_bool(obj.get("IsCompany"))
        return PpgListElement(id_ppg, meter_number, contract_number, has_t12, reading_added, tariff, has_history, type, id_local, client_number, installation_number, color, agreement_name, can_create_home_assistant, add_reading_mode, is_in_migration, is_in_migration_rk, is_in_migration_rw, is_company)

    def to_dict(self) -> dict:
        result: dict = {"IdPPG": from_str(self.id_ppg), "MeterNumber": from_str(self.meter_number),
                        "ContractNumber": from_str(self.contract_number), "HasT12": from_bool(self.has_t12),
                        "ReadingAdded": from_bool(self.reading_added), "Tariff": from_str(self.tariff),
                        "HasHistory": from_bool(self.has_history), "Type": from_str(self.type),
                        "IdLocal": from_str(str(self.id_local)), "ClientNumber": from_str(str(self.client_number)),
                        "InstallationNumber": from_str(self.installation_number), "Color": from_str(self.color),
                        "AgreementName": from_str(self.agreement_name),
                        "CanCreateHomeAssistant": from_bool(self.can_create_home_assistant),
                        "AddReadingMode": from_str(self.add_reading_mode),
                        "IsInMigration": from_bool(self.is_in_migration),
                        "IsInMigrationRK": from_bool(self.is_in_migration_rk),
                        "IsInMigrationRW": from_bool(self.is_in_migration_rw), "IsCompany": from_bool(self.is_company)}
        return result


@dataclass
class PpgList:
    ppg_list: List[PpgListElement]
    code: int
    message: None
    display_to_end_user: bool
    end_user_message: None
    token_expire_date: datetime
    token_expire_date_utc: datetime

    @staticmethod
    def from_dict(obj: Any) -> 'PpgList':
        ppg_list = from_list(PpgListElement.from_dict, obj.get("PpgList"))
        code = from_int(obj.get("Code"))
        message = from_none(obj.get("Message"))
        display_to_end_user = from_bool(obj.get("DisplayToEndUser"))
        end_user_message = from_none(obj.get("EndUserMessage"))
        token_expire_date = from_datetime(obj.get("TokenExpireDate"))
        token_expire_date_utc = from_datetime(obj.get("TokenExpireDateUtc"))
        return PpgList(ppg_list, code, message, display_to_end_user, end_user_message, token_expire_date, token_expire_date_utc)

    def to_dict(self) -> dict:
        result: dict = {"PpgList": from_list(lambda x: to_class(PpgListElement, x), self.ppg_list),
                        "Code": from_int(self.code), "Message": from_none(self.message),
                        "DisplayToEndUser": from_bool(self.display_to_end_user),
                        "EndUserMessage": from_none(self.end_user_message),
                        "TokenExpireDate": self.token_expire_date.isoformat(),
                        "TokenExpireDateUtc": self.token_expire_date_utc.isoformat()}
        return result


def ppg_list_from_dict(s: Any) -> PpgList:
    return PpgList.from_dict(s)


def ppg_list_to_dict(x: PpgList) -> Any:
    return to_class(PpgList, x)
