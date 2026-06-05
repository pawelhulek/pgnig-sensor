#!/usr/bin/env python3
"""Test OrlenID auth method."""
import logging
import sys
import getpass

sys.path.insert(0, "custom_components")
from pgnig_gas_sensor.auth import AuthRegistry


def test_method(username, password, method_id):
    print(f"\n{'='*60}")
    print(f"Testing auth method: {method_id}")
    print(f"{'='*60}")

    method_cls = AuthRegistry.get(method_id)
    if not method_cls:
        print(f"Auth method '{method_id}' not found!")
        return None

    auth = method_cls(username, password)

    try:
        token = auth.login()
        if token:
            print(f"LOGIN OK! Token: {token[:50]}...")
            return token
        else:
            print("LOGIN FAILED: Empty token returned")
            return None
    except Exception as e:
        print(f"LOGIN FAILED: {e}")
        return None


def test_data_fetch(username, password, method_id):
    print(f"\n{'='*60}")
    print(f"Testing data fetch with method: {method_id}")
    print(f"{'='*60}")

    method_cls = AuthRegistry.get(method_id)
    auth = method_cls(username, password)

    try:
        token = auth.login()
    except Exception as e:
        print(f"LOGIN FAILED: {e}")
        return

    if not token:
        print("No token, skipping data fetch")
        return

    BASE_URL = "https://ebok.myorlen.pl"
    session = auth._session
    headers = {"AuthToken": token}

    # Fetch meter list
    print("\n--- Meter list ---")
    resp = session.get(f"{BASE_URL}/crm/get-ppg-list?api-version=3.0", headers=headers, timeout=30)
    if resp.ok:
        data = resp.json()
        meters = data.get("PpgList", [])
        print(f"Found {len(meters)} meter(s):")
        for m in meters:
            print(f"  - {m.get('MeterNumber')} | tariff: {m.get('Tariff')} | idPPG: {m.get('IdPPG')}")
    else:
        print(f"Failed: {resp.status_code} {resp.text[:200]}")

    # Fetch invoices
    print("\n--- Invoices ---")
    resp = session.get(f"{BASE_URL}/crm/get-invoices-v2?pageNumber=1&pageSize=12&api-version=3.0", headers=headers, timeout=30)
    if resp.ok:
        data = resp.json()
        invoices = data.get("InvoicesList", [])
        print(f"Found {len(invoices)} invoice(s):")
        for inv in invoices[:3]:
            print(f"  - {inv.get('Number')}: {inv.get('Date')}, {inv.get('GrossAmount')} PLN")
    else:
        print(f"Failed: {resp.status_code}")


def main():
    methods = AuthRegistry.list()
    print("Available auth methods:")
    for m in methods:
        print(f"  - {m.id}: {m.name}")

    if len(sys.argv) >= 4:
        username = sys.argv[1]
        password = sys.argv[2]
        method = sys.argv[3]
        test_data_fetch(username, password, method)
    elif len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
        for m in methods:
            test_method(username, password, m.id)
    else:
        username = input("Username: ")
        password = getpass.getpass("Password: ")
        print()
        if len(methods) == 1:
            test_data_fetch(username, password, methods[0].id)
        else:
            for m in methods:
                test_method(username, password, m.id)

    print("\nDone.")


if __name__ == "__main__":
    level = logging.DEBUG if "-v" in sys.argv else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    if "-v" in sys.argv:
        sys.argv.remove("-v")
    main()
