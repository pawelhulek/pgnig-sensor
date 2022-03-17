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


def from_float(x: Any) -> float:
    assert isinstance(x, (float, int)) and not isinstance(x, bool)
    return float(x)


def from_int(x: Any) -> int:
    assert isinstance(x, int) and not isinstance(x, bool)
    return x


def from_bool(x: Any) -> bool:
    assert isinstance(x, bool)
    return x


def from_none(x: Any) -> Any:
    assert x is None
    return x


def to_float(x: Any) -> float:
    assert isinstance(x, float)
    return x


def from_list(f: Callable[[Any], T], x: Any) -> List[T]:
    assert isinstance(x, list)
    return [f(y) for y in x]


def to_class(c: Type[T], x: Any) -> dict:
    assert isinstance(x, c)
    return cast(Any, x).to_dict()


@dataclass
class InvoicesList:
    number: str
    date: datetime
    sell_date: datetime
    gross_amount: float
    amount_to_pay: int
    wear: int
    wear_kwh: int
    paying_deadline_date: datetime
    start_date: datetime
    end_date: datetime
    is_paid: bool
    id_pp: int
    type: str
    temp_type: str
    days_remaining_to_deadline: int
    has_iban: bool
    status: str
    pdf_exists: bool
    is_interest_note: bool
    color: str
    agreement_name: str
    agreement_number: str
    is_additional_agreement: bool
    agreement_end_date: None
    agreement_expired: bool
    pdf_print_allowed: bool
    payment_process_allowed: bool
    agreement_has_card: bool
    automatic_payment_date: datetime
    is_insurance_policy: bool
    is_lawyer_agreement: bool

    @staticmethod
    def from_dict(obj: Any) -> 'InvoicesList':
        assert isinstance(obj, dict)
        number = from_str(obj.get("Number"))
        date = from_datetime(obj.get("Date"))
        sell_date = from_datetime(obj.get("SellDate"))
        gross_amount = from_float(obj.get("GrossAmount"))
        amount_to_pay = from_int(obj.get("AmountToPay"))
        wear = from_int(obj.get("Wear"))
        wear_kwh = from_int(obj.get("WearKWH"))
        paying_deadline_date = from_datetime(obj.get("PayingDeadlineDate"))
        start_date = from_datetime(obj.get("StartDate"))
        end_date = from_datetime(obj.get("EndDate"))
        is_paid = from_bool(obj.get("IsPaid"))
        id_pp = int(from_str(obj.get("IdPP")))
        type = from_str(obj.get("Type"))
        temp_type = from_str(obj.get("TempType"))
        days_remaining_to_deadline = from_int(obj.get("DaysRemainingToDeadline"))
        has_iban = from_bool(obj.get("HasIban"))
        status = from_str(obj.get("Status"))
        pdf_exists = from_bool(obj.get("PdfExists"))
        is_interest_note = from_bool(obj.get("IsInterestNote"))
        color = from_str(obj.get("Color"))
        agreement_name = from_str(obj.get("AgreementName"))
        agreement_number = from_str(obj.get("AgreementNumber"))
        is_additional_agreement = from_bool(obj.get("IsAdditionalAgreement"))
        agreement_end_date = from_none(obj.get("AgreementEndDate"))
        agreement_expired = from_bool(obj.get("AgreementExpired"))
        pdf_print_allowed = from_bool(obj.get("PDFPrintAllowed"))
        payment_process_allowed = from_bool(obj.get("PaymentProcessAllowed"))
        agreement_has_card = from_bool(obj.get("AgreementHasCard"))
        automatic_payment_date = from_datetime(obj.get("AutomaticPaymentDate"))
        is_insurance_policy = from_bool(obj.get("IsInsurancePolicy"))
        is_lawyer_agreement = from_bool(obj.get("IsLawyerAgreement"))
        return InvoicesList(number, date, sell_date, gross_amount, amount_to_pay, wear, wear_kwh, paying_deadline_date,
                            start_date, end_date, is_paid, id_pp, type, temp_type, days_remaining_to_deadline, has_iban,
                            status, pdf_exists, is_interest_note, color, agreement_name, agreement_number,
                            is_additional_agreement, agreement_end_date, agreement_expired, pdf_print_allowed,
                            payment_process_allowed, agreement_has_card, automatic_payment_date, is_insurance_policy,
                            is_lawyer_agreement)

    def to_dict(self) -> dict:
        result: dict = {"Number": from_str(self.number), "Date": self.date.isoformat(),
                        "SellDate": self.sell_date.isoformat(), "GrossAmount": to_float(self.gross_amount),
                        "AmountToPay": from_int(self.amount_to_pay), "Wear": from_int(self.wear),
                        "WearKWH": from_int(self.wear_kwh), "PayingDeadlineDate": self.paying_deadline_date.isoformat(),
                        "StartDate": self.start_date.isoformat(), "EndDate": self.end_date.isoformat(),
                        "IsPaid": from_bool(self.is_paid), "IdPP": from_str(str(self.id_pp)),
                        "Type": from_str(self.type), "TempType": from_str(self.temp_type),
                        "DaysRemainingToDeadline": from_int(self.days_remaining_to_deadline),
                        "HasIban": from_bool(self.has_iban), "Status": from_str(self.status),
                        "PdfExists": from_bool(self.pdf_exists), "IsInterestNote": from_bool(self.is_interest_note),
                        "Color": from_str(self.color), "AgreementName": from_str(self.agreement_name),
                        "AgreementNumber": from_str(self.agreement_number),
                        "IsAdditionalAgreement": from_bool(self.is_additional_agreement),
                        "AgreementEndDate": from_none(self.agreement_end_date),
                        "AgreementExpired": from_bool(self.agreement_expired),
                        "PDFPrintAllowed": from_bool(self.pdf_print_allowed),
                        "PaymentProcessAllowed": from_bool(self.payment_process_allowed),
                        "AgreementHasCard": from_bool(self.agreement_has_card),
                        "AutomaticPaymentDate": self.automatic_payment_date.isoformat(),
                        "IsInsurancePolicy": from_bool(self.is_insurance_policy),
                        "IsLawyerAgreement": from_bool(self.is_lawyer_agreement)}
        return result


@dataclass
class Invoices:
    has_non_paid_forecast: bool
    allow_load_after30_days: bool
    invoices_list: List[InvoicesList]
    code: int
    message: None
    display_to_end_user: bool
    end_user_message: None
    token_expire_date: datetime
    token_expire_date_utc: datetime

    @staticmethod
    def from_dict(obj: Any) -> 'Invoices':
        assert isinstance(obj, dict)
        has_non_paid_forecast = from_bool(obj.get("HasNonPaidForecast"))
        allow_load_after30_days = from_bool(obj.get("AllowLoadAfter30Days"))
        invoices_list = from_list(InvoicesList.from_dict, obj.get("InvoicesList"))
        code = from_int(obj.get("Code"))
        message = from_none(obj.get("Message"))
        display_to_end_user = from_bool(obj.get("DisplayToEndUser"))
        end_user_message = from_none(obj.get("EndUserMessage"))
        token_expire_date = from_datetime(obj.get("TokenExpireDate"))
        token_expire_date_utc = from_datetime(obj.get("TokenExpireDateUtc"))
        return Invoices(has_non_paid_forecast, allow_load_after30_days, invoices_list, code, message,
                        display_to_end_user, end_user_message, token_expire_date, token_expire_date_utc)

    def to_dict(self) -> dict:
        result: dict = {"HasNonPaidForecast": from_bool(self.has_non_paid_forecast),
                        "AllowLoadAfter30Days": from_bool(self.allow_load_after30_days),
                        "InvoicesList": from_list(lambda x: to_class(InvoicesList, x), self.invoices_list),
                        "Code": from_int(self.code), "Message": from_none(self.message),
                        "DisplayToEndUser": from_bool(self.display_to_end_user),
                        "EndUserMessage": from_none(self.end_user_message),
                        "TokenExpireDate": self.token_expire_date.isoformat(),
                        "TokenExpireDateUtc": self.token_expire_date_utc.isoformat()}
        return result


def invoices_from_dict(s: Any) -> Invoices:
    return Invoices.from_dict(s)


def invoices_to_dict(x: Invoices) -> Any:
    return to_class(Invoices, x)
