from copy import deepcopy
from pathlib import Path
import json

import pytest

from vehicle_swdl.models import (
    FaultPlan,
    FormatError,
    VehicleDefinition,
    load_manifest,
    read_json,
    version_at_least,
    version_tuple,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", (1,)), ("1.2", (1, 2)), ("0.0.1", (0, 0, 1)), ("10.20.30", (10, 20, 30))],
)
def test_version_tuple_accepts_dotted_numeric_versions(value, expected):
    assert version_tuple(value) == expected


@pytest.mark.parametrize("value", ["", "v1.0", "1.x", "1..2", "1.2-beta"])
def test_version_tuple_rejects_unsupported_formats(value):
    with pytest.raises(FormatError):
        version_tuple(value)


@pytest.mark.parametrize(
    ("actual", "minimum", "expected"),
    [
        ("2.0", "2.0.0", True),
        ("2.1.0", "2.0.9", True),
        ("1.9.9", "2.0.0", False),
        ("3.0.0", "3", True),
        ("3.0.0", "3.0.1", False),
    ],
)
def test_version_comparison(actual, minimum, expected):
    assert version_at_least(actual, minimum) is expected


def test_manifest_loads_and_validates_packages(manifest):
    assert manifest.campaign_id == "complete-vehicle-baseline-2026.40.0"
    assert [image.ecu_id for image in manifest.images] == ["gateway", "ccm", "infotainment"]
    assert sum(image.size for image in manifest.images) == 151


def test_manifest_rejects_declared_size_mismatch(example_dir, tmp_path):
    document = read_json(example_dir / "manifest.json")
    document["images"][0]["size"] = 999
    target = tmp_path / "manifest.json"
    package_dir = tmp_path / "packages"
    package_dir.mkdir()
    for source in (example_dir / "packages").iterdir():
        (package_dir / source.name).write_bytes(source.read_bytes())
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(FormatError, match="size mismatch"):
        load_manifest(target)


def test_manifest_rejects_hash_mismatch(example_dir, tmp_path):
    document = read_json(example_dir / "manifest.json")
    document["images"][0]["sha256"] = "0" * 64
    target = tmp_path / "manifest.json"
    package_dir = tmp_path / "packages"
    package_dir.mkdir()
    for source in (example_dir / "packages").iterdir():
        (package_dir / source.name).write_bytes(source.read_bytes())
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(FormatError, match="SHA-256 mismatch"):
        load_manifest(target)


def test_manifest_rejects_path_escape(example_dir, tmp_path):
    document = read_json(example_dir / "manifest.json")
    document["images"][0]["file"] = "../outside.bin"
    (tmp_path / "outside.bin").write_bytes(b"x")
    document["images"][0]["size"] = 1
    document["images"][0]["sha256"] = "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    target = manifest_dir / "manifest.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(FormatError, match="escapes"):
        load_manifest(target)


def test_vehicle_requires_unique_ecu_ids(example_dir):
    document = read_json(example_dir / "vehicle.json")
    document["ecus"].append(deepcopy(document["ecus"][0]))
    with pytest.raises(FormatError, match="unique"):
        VehicleDefinition.from_mapping(document)


def test_vehicle_requires_populated_active_slot(example_dir):
    document = read_json(example_dir / "vehicle.json")
    document["ecus"][0]["slot_versions"]["A"] = None
    with pytest.raises(FormatError, match="populated"):
        VehicleDefinition.from_mapping(document)


def test_fault_plan_parses_network_and_health_faults():
    faults = FaultPlan.from_mapping(
        {"drop_once": {"gateway": [1]}, "corrupt": {"ccm": [0]}, "health_check_fail": ["ccm"]}
    )
    assert faults.drop_once == {"gateway": (1,)}
    assert faults.corrupt == {"ccm": (0,)}
    assert faults.health_check_fail == ("ccm",)


def test_fault_plan_rejects_negative_indices():
    with pytest.raises(FormatError):
        FaultPlan.from_mapping({"drop_always": {"gateway": [-1]}})


def test_read_json_rejects_non_object(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(FormatError, match="object"):
        read_json(path)
