"""Tests for auth module: AuthRegistry, AuthMethod, device_id."""
import re

from custom_components.pgnig_gas_sensor.auth import (
    AuthRegistry,
    AuthMethod,
    device_id,
    AuthMethodInfo,
)


def test_device_id_format():
    result = device_id("test@example.com")
    assert re.match(r"^[0-9a-f]{32}$", result)


def test_device_id_is_random():
    a = device_id("same@user.com")
    b = device_id("same@user.com")
    assert a != b


def test_auth_registry_contains_registered_methods():
    ids = AuthRegistry.get_ids()
    assert "api_login" in ids
    assert "orlen_id" in ids


def test_auth_registry_get_known():
    cls = AuthRegistry.get("api_login")
    assert cls is not None
    assert issubclass(cls, AuthMethod)


def test_auth_registry_get_unknown():
    assert AuthRegistry.get("nonexistent_method") is None


def test_auth_registry_list():
    infos = AuthRegistry.list()
    assert len(infos) >= 2
    info_ids = [i.id for i in infos]
    assert "api_login" in info_ids
    assert "orlen_id" in info_ids
    for info in infos:
        assert isinstance(info, AuthMethodInfo)


def test_auth_registry_get_ids():
    ids = AuthRegistry.get_ids()
    assert "api_login" in ids
    assert "orlen_id" in ids
    assert len(ids) >= 2


def test_auth_method_abc_cannot_instantiate():
    try:
        AuthMethod()
        assert False, "Should have raised TypeError"
    except TypeError:
        pass
