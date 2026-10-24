from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

import pytest

from vehicle_swdl.calibration_release import build_release, validate_calibration, verify_release
from vehicle_swdl.cli import main
from vehicle_swdl.models import FormatError


@pytest.fixture
def inputs(example_dir, tmp_path):
    source = tmp_path / "inputs"
    shutil.copytree(example_dir, source)
    return source


def validate(source):
    return validate_calibration(source / "manifest.json", source / "calibration_contract.json",
                                source / "calibration.json")


def build(source, destination):
    return build_release(source / "manifest.json", source / "calibration_contract.json",
                         source / "calibration.json", destination)


def change(source, filename, path, value):
    target = source / filename
    data = json.loads(target.read_text())
    current = data
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    target.write_text(json.dumps(data), encoding="utf-8")


def test_reference_calibration_targets_the_declared_software(inputs):
    result = validate(inputs)
    assert result == {"calibration_id": "ccm-driveability-2026.10", "contract_id": "ccm-driveability-v1",
                      "ecu_id": "ccm", "software_version": "2.2.0", "parameter_count": 3}


@pytest.mark.parametrize("filename,path,value,code", [
    ("calibration.json", ["software_version"], "2.3.0", "CAL_SOFTWARE_MISMATCH"),
    ("calibration.json", ["hardware_id"], "OTHER", "CAL_HARDWARE_MISMATCH"),
    ("calibration.json", ["ecu_id"], "other", "CAL_ECU_MISMATCH"),
    ("calibration.json", ["contract_id"], "other", "CAL_CONTRACT_MISMATCH"),
    ("calibration.json", ["schema_version"], True, "UNSUPPORTED_SCHEMA"),
    ("calibration.json", ["parameters", 0, "unit"], "kNm", "CAL_UNIT_MISMATCH"),
    ("calibration.json", ["parameters", 0, "value"], -1, "CAL_VALUE_OUT_OF_RANGE"),
    ("calibration.json", ["parameters", 0, "value"], 601, "CAL_VALUE_OUT_OF_RANGE"),
    ("calibration.json", ["parameters", 0, "value"], True, "INVALID_NUMBER"),
    ("calibration.json", ["parameters", 0, "value"], float("inf"), "NON_FINITE_NUMBER"),
    ("calibration.json", ["parameters", 0, "value"], float("nan"), "NON_FINITE_NUMBER"),
    ("calibration.json", ["parameters", 0, "value"], 10 ** 500, "NON_FINITE_NUMBER"),
    ("calibration.json", ["parameters", 0, "name"], "other", "CAL_UNKNOWN_PARAMETER"),
    ("calibration.json", ["parameters"], [], "CAL_MISSING_PARAMETER"),
    ("calibration.json", ["parameters"], None, "INVALID_PARAMETERS"),
    ("calibration.json", ["calibration_id"], "../escape", "INVALID_IDENTIFIER"),
    ("calibration_contract.json", ["parameters", "torque_limit_nm", "minimum"], 700, "INVALID_CONTRACT"),
    ("calibration_contract.json", ["parameters", "torque_limit_nm", "unit"], "", "INVALID_CONTRACT"),
    ("calibration_contract.json", ["compatible_software"], [], "INVALID_CONTRACT"),
    ("calibration_contract.json", ["compatible_hardware"], ["OTHER"], "CAL_HARDWARE_MISMATCH"),
])
def test_invalid_calibration_is_rejected(inputs, filename, path, value, code):
    change(inputs, filename, path, value)
    with pytest.raises(FormatError, match=code):
        validate(inputs)


@pytest.mark.parametrize("value", [0, 600])
def test_inclusive_range_boundaries_are_valid(inputs, value):
    change(inputs, "calibration.json", ["parameters", 0, "value"], value)
    assert validate(inputs)["parameter_count"] == 3


def test_duplicate_parameter_names_are_rejected(inputs):
    target = inputs / "calibration.json"
    data = json.loads(target.read_text())
    data["parameters"].append(deepcopy(data["parameters"][0]))
    target.write_text(json.dumps(data))
    with pytest.raises(FormatError, match="CAL_DUPLICATE_PARAMETER"):
        validate(inputs)


def test_duplicate_json_keys_are_not_silently_overwritten(inputs):
    target = inputs / "calibration.json"
    target.write_text(target.read_text().replace('"schema_version": 1,',
                                               '"schema_version": 1, "schema_version": 1,'))
    with pytest.raises(FormatError, match="DUPLICATE_JSON_KEY"):
        validate(inputs)


def test_missing_input_is_a_format_error(inputs):
    (inputs / "calibration.json").unlink()
    with pytest.raises(FormatError, match="INPUT_UNREADABLE"):
        validate(inputs)


def test_release_is_reproducible_and_can_be_verified(inputs, tmp_path):
    first, second = tmp_path / "one.zip", tmp_path / "two.zip"
    one, two = build(inputs, first), build(inputs, second)
    assert first.read_bytes() == second.read_bytes()
    assert one == two
    assert one["bundle_sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert one["artifact_count"] == 5
    assert verify_release(first)["verified"] is True
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist())
        metadata = json.loads(archive.read("release.json"))
        assert metadata["update_order"] == ["gateway", "ccm", "infotainment"]
        assert all(not Path(i["path"]).is_absolute() for i in metadata["artifacts"])


def rewrite(bundle, modify):
    with zipfile.ZipFile(bundle) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    modify(files)
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)


def test_changed_artifact_fails_inventory_integrity(inputs, tmp_path):
    target = tmp_path / "release.zip"
    build(inputs, target)
    rewrite(target, lambda files: files.update({"calibration/values.json": b"{}"}))
    with pytest.raises(FormatError, match="ARTIFACT_INTEGRITY_MISMATCH"):
        verify_release(target)


def test_calibration_is_rechecked_even_if_inventory_hashes_are_updated(inputs, tmp_path):
    target = tmp_path / "release.zip"
    build(inputs, target)
    def modify(files):
        values = json.loads(files["calibration/values.json"])
        values["parameters"][0]["unit"] = "wrong"
        payload = json.dumps(values).encode()
        files["calibration/values.json"] = payload
        metadata = json.loads(files["release.json"])
        for artifact in metadata["artifacts"]:
            if artifact["path"] == "calibration/values.json":
                artifact.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        files["release.json"] = json.dumps(metadata).encode()
    rewrite(target, modify)
    with pytest.raises(FormatError, match="CAL_UNIT_MISMATCH"):
        verify_release(target)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("update_order", [{}]),
    ("update_order", ["ccm", "gateway", "infotainment"]),
    ("calibration_id", "other"), ("software", []), ("artifacts", []),
])
def test_invalid_release_metadata_is_rejected(inputs, tmp_path, field, value):
    target = tmp_path / "release.zip"
    build(inputs, target)
    def modify(files):
        metadata = json.loads(files["release.json"])
        metadata[field] = value
        files["release.json"] = json.dumps(metadata).encode()
    rewrite(target, modify)
    with pytest.raises(FormatError):
        verify_release(target)


def test_archive_traversal_names_are_rejected(inputs, tmp_path):
    target = tmp_path / "release.zip"
    build(inputs, target)
    rewrite(target, lambda files: files.update({"../escape": b"ignored"}))
    with pytest.raises(FormatError, match="INVALID_ARCHIVE_PATH"):
        verify_release(target)
    assert not (tmp_path / "escape").exists()


def test_non_target_software_metadata_still_requires_a_string_version(inputs, tmp_path):
    target = tmp_path / "release.zip"
    build(inputs, target)
    def modify(files):
        metadata = json.loads(files["release.json"])
        gateway = next(i for i in metadata["software"] if i["ecu_id"] == "gateway")
        gateway["version"] = 5
        files["release.json"] = json.dumps(metadata).encode()
    rewrite(target, modify)
    with pytest.raises(FormatError, match="software version must be a string"):
        verify_release(target)


def test_invalid_calibration_does_not_replace_an_existing_release(inputs, tmp_path):
    target = tmp_path / "release.zip"
    build(inputs, target)
    original = target.read_bytes()
    change(inputs, "calibration.json", ["hardware_id"], "OTHER")
    with pytest.raises(FormatError):
        build(inputs, target)
    assert target.read_bytes() == original


def test_unreadable_zip_is_a_format_error(tmp_path):
    target = tmp_path / "not-a-zip"
    target.write_bytes(b"invalid")
    with pytest.raises(FormatError, match="BUNDLE_UNREADABLE"):
        verify_release(target)


def test_release_cli_build_validate_and_verify(inputs, tmp_path, capsys):
    common = ["--manifest", str(inputs / "manifest.json"), "--contract",
              str(inputs / "calibration_contract.json"), "--calibration", str(inputs / "calibration.json")]
    assert main(["validate-calibration", *common]) == 0
    assert json.loads(capsys.readouterr().out)["parameter_count"] == 3
    bundle, report = tmp_path / "cli.zip", tmp_path / "report.json"
    assert main(["build-release", *common, "--output", str(bundle), "--report", str(report)]) == 0
    assert json.loads(report.read_text()) == json.loads(capsys.readouterr().out)
    assert main(["verify-release", "--bundle", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["verified"]
    change(inputs, "calibration.json", ["hardware_id"], "OTHER")
    assert main(["validate-calibration", *common]) == 2
    assert "CAL_HARDWARE_MISMATCH" in capsys.readouterr().err
