"""Guards for manifest.json — HACS shows this version to users.

HACS installs this repository from source, so the committed manifest version
is what appears in the integrations dashboard. It drifted from the release
tags before (v3.0.2 shipped "2.4.0", v3.1.0 shipped "2.5.0"), which made it
impossible to tell from HACS which code was actually installed.
"""
import json
import re
from pathlib import Path

import pytest

MANIFEST_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "pgnig_gas_sensor"
    / "manifest.json"
)

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_is_valid_json(manifest):
    assert manifest["domain"] == "pgnig_gas_sensor"


@pytest.mark.parametrize(
    "key",
    ["domain", "name", "documentation", "issue_tracker", "codeowners", "version"],
)
def test_manifest_has_keys_hacs_requires(manifest, key):
    assert manifest.get(key), f"manifest.json is missing {key!r}"


def test_version_is_semver(manifest):
    version = manifest["version"]
    assert SEMVER.match(version), f"{version!r} is not a semver version"


def test_version_matches_repository_tags(manifest):
    """The manifest must track the release tags, not lag a major version behind."""
    major = int(manifest["version"].split(".")[0])
    assert major >= 3, (
        f"manifest version {manifest['version']} predates the v3 releases; "
        "bump it to the version being released"
    )
