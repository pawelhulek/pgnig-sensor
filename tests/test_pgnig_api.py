"""Tests for PgnigApi class with mocked auth and HTTP."""
from unittest.mock import MagicMock, patch

import pytest

from custom_components.pgnig_gas_sensor.PgnigApi import PgnigApi


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.login.return_value = "test-token"
    auth.session = MagicMock()
    auth.session.get.return_value.ok = True
    auth.session.get.return_value.json.return_value = {
        "PpgList": [{
            "IdPPG": "123", "MeterNumber": "METER1", "ContractNumber": "C1",
            "HasT12": True, "ReadingAdded": True, "Tariff": "T1",
            "HasHistory": True, "Type": "G", "IdLocal": "1",
            "ClientNumber": "100", "InstallationNumber": "INST1",
            "Color": "red", "AgreementName": "Main",
            "CanCreateHomeAssistant": True, "AddReadingMode": "auto",
            "IsInMigration": False, "IsInMigrationRK": False,
            "IsInMigrationRW": False, "IsCompany": False,
        }],
        "Code": 0, "Message": None, "DisplayToEndUser": False,
        "EndUserMessage": None,
        "TokenExpireDate": "2026-06-01T00:00:00",
        "TokenExpireDateUtc": "2026-06-01T00:00:00",
    }
    return auth


@pytest.fixture
def api(mock_auth):
    with patch(
        "custom_components.pgnig_gas_sensor.PgnigApi.AuthRegistry.get",
        return_value=MagicMock(return_value=mock_auth),
    ):
        return PgnigApi("user", "pass", "api_login")


def test_init_raises_on_unknown_method():
    with pytest.raises(ValueError, match="Unknown auth method"):
        PgnigApi("u", "p", "nonexistent")


def test_login_delegates_to_auth(api, mock_auth):
    token = api.login()
    assert token == "test-token"
    mock_auth.login.assert_called_once()


def test_meter_list_success(api, mock_auth):
    ppg = api.meterList()
    assert ppg is not None
    assert len(ppg.ppg_list) == 1
    assert ppg.ppg_list[0].meter_number == "METER1"
    mock_auth.session.get.assert_called_once()


def test_meter_list_raises_on_no_token(api, mock_auth):
    mock_auth.login.return_value = ""
    with pytest.raises(RuntimeError, match="Login failed - no token received"):
        api.meterList()


def test_meter_list_raises_on_http_error(api, mock_auth):
    mock_auth.session.get.return_value.ok = False
    mock_auth.session.get.return_value.status_code = 500
    mock_auth.session.get.return_value.text = "Server Error"
    with pytest.raises(RuntimeError, match="Meter list failed with status 500"):
        api.meterList()


def test_reading_for_meter_success(api, mock_auth):
    mock_auth.session.get.return_value.json.return_value = {
        "MeterReadings": [{
            "Status": "OK", "ReadingDateLocal": "2026-05-01T00:00:00",
            "ReadingDateUtc": "2026-05-01T00:00:00", "PpId": "1",
            "Value": 123, "Value2": None, "Value3": None,
            "MeterNumber": "METER1", "RegionCode": "PL",
            "Wear": 50, "Type": "G", "Color": "red",
        }],
        "Code": 0, "Message": None, "DisplayToEndUser": False,
        "EndUserMessage": None,
        "TokenExpireDate": "2026-06-01T00:00:00",
        "TokenExpireDateUtc": "2026-06-01T00:00:00",
    }
    readings = api.readingForMeter("123")
    assert readings is not None
    assert len(readings.meter_readings) == 1
    assert readings.meter_readings[0].value == 123


def test_reading_for_meter_raises_on_no_token(api, mock_auth):
    mock_auth.login.return_value = ""
    with pytest.raises(RuntimeError, match="Login failed - no token received"):
        api.readingForMeter("123")


def test_reading_for_meter_raises_on_http_error(api, mock_auth):
    mock_auth.session.get.return_value.ok = False
    mock_auth.session.get.return_value.status_code = 404
    with pytest.raises(RuntimeError, match="Reading failed with status 404"):
        api.readingForMeter("123")


def test_invoices_success(api, mock_auth):
    mock_auth.session.get.return_value.json.return_value = {
        "InvoicesList": [{
            "Number": "INV001", "Date": "2026-04-01T00:00:00",
            "SellDate": "2026-04-01T00:00:00",
            "GrossAmount": 150.0, "AmountToPay": 150.0,
            "Wear": 0.0, "WearKWH": 100.0, "WearM3": 50.0,
            "PayingDeadlineDate": "2026-05-01T00:00:00",
            "StartDate": "2026-03-01T00:00:00",
            "EndDate": "2026-03-31T00:00:00",
            "IsPaid": False, "IdPP": "1", "Type": "G", "TempType": "G",
            "DaysRemainingToDeadline": 10, "HasIban": True, "Iban": "PL00",
            "Status": "OPEN", "PdfExists": True,
            "IsInterestNote": False, "IsCreditNote": False,
            "Color": "red", "AgreementName": "Main",
            "AgreementNumber": "A1", "IsAdditionalAgreement": False,
            "AgreementEndDate": None, "AgreementExpired": False,
            "PDFPrintAllowed": True, "PaymentProcessAllowed": True,
            "AgreementHasCard": False, "AutomaticPaymentDate": None,
            "IsInsurancePolicy": False, "IsLawyerAgreement": False,
        }],
        "HasNonPaidForecast": False, "AllowLoadAfter30Days": True,
        "AllowLoadAfter30DaysFilter": False,
        "Code": 0, "Message": None, "DisplayToEndUser": False,
        "EndUserMessage": None,
        "TokenExpireDate": "2026-06-01T00:00:00",
        "TokenExpireDateUtc": "2026-06-01T00:00:00",
    }
    inv = api.invoices()
    assert inv is not None
    assert len(inv.invoices_list) == 1
    assert inv.invoices_list[0].number == "INV001"


def test_invoices_raises_on_no_token(api, mock_auth):
    mock_auth.login.return_value = ""
    with pytest.raises(RuntimeError, match="Login failed - no token received"):
        api.invoices()


def test_invoices_raises_on_http_error(api, mock_auth):
    mock_auth.session.get.return_value.ok = False
    mock_auth.session.get.return_value.status_code = 500
    with pytest.raises(RuntimeError, match="Invoices failed with status 500"):
        api.invoices()


def test_api_uses_auth_session(api, mock_auth):
    _ = api.meterList()
    mock_auth.session.get.assert_called_once()
    call_args = mock_auth.session.get.call_args
    headers = call_args[1]["headers"]
    assert headers["AuthToken"] == "test-token"
