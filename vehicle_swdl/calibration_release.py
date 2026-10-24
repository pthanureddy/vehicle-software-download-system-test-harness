"""Contract-checked calibration data and reproducible software release bundles.

Only repository-defined, synthetic calibration contracts are supported. Hashes
detect accidental corruption; bundles are not signed or authenticated.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any
import zipfile

from .models import FormatError, load_manifest, version_tuple
from .topology import dependency_order

MAX_BUNDLE_BYTES = 16 * 1024 * 1024
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")


def _fail(code: str, message: str) -> None:
    raise FormatError(f"{code}: {message}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", key)
        result[key] = value
    return result


def _constant(value: str) -> None:
    _fail("NON_FINITE_NUMBER", value)


def _json(payload: bytes) -> dict[str, Any]:
    try:
        result = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError) as exc:
        raise FormatError(f"INVALID_JSON: {exc}") from exc
    if not isinstance(result, dict):
        _fail("INVALID_DOCUMENT", "expected a JSON object")
    return result


def _read(path: Path) -> dict[str, Any]:
    try:
        return _json(path.read_bytes())
    except OSError as exc:
        raise FormatError(f"INPUT_UNREADABLE: {path.name}") from exc


def _keys(data: Any, expected: set[str], label: str) -> None:
    if not isinstance(data, dict) or set(data) != expected:
        _fail("INVALID_FIELDS", f"{label} requires exactly {sorted(expected)}")


def _token(value: Any) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        _fail("INVALID_IDENTIFIER", repr(value))
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("INVALID_NUMBER", repr(value))
    try:
        number = float(value)
    except OverflowError as exc:
        raise FormatError("NON_FINITE_NUMBER: numeric overflow") from exc
    if not math.isfinite(number):
        _fail("NON_FINITE_NUMBER", repr(value))
    return number


def _validate(contract: dict, calibration: dict, software: dict[str, dict]) -> dict:
    _keys(contract, {"schema_version", "contract_id", "ecu_id", "compatible_software",
                     "compatible_hardware", "parameters"}, "contract")
    _keys(calibration, {"schema_version", "calibration_id", "contract_id", "ecu_id",
                        "software_version", "hardware_id", "parameters"}, "calibration")
    for data in (contract, calibration):
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            _fail("UNSUPPORTED_SCHEMA", "schema_version must be integer 1")
        _token(data["contract_id"])
        _token(data["ecu_id"])
    _token(calibration["calibration_id"])
    if calibration["contract_id"] != contract["contract_id"]:
        _fail("CAL_CONTRACT_MISMATCH", "calibration names another contract")
    if calibration["ecu_id"] != contract["ecu_id"] or calibration["ecu_id"] not in software:
        _fail("CAL_ECU_MISMATCH", "target ECU is not in the software release")
    for field in ("compatible_software", "compatible_hardware"):
        values = contract[field]
        if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
            _fail("INVALID_CONTRACT", f"{field} must contain strings")
    for version in contract["compatible_software"]:
        version_tuple(version)
    if not isinstance(calibration["software_version"], str):
        _fail("CAL_SOFTWARE_MISMATCH", "software version must be a string")
    version_tuple(calibration["software_version"])
    image = software[calibration["ecu_id"]]
    if (calibration["software_version"] != image["version"] or
            calibration["software_version"] not in contract["compatible_software"]):
        _fail("CAL_SOFTWARE_MISMATCH", "exact software version is incompatible")
    hardware = calibration["hardware_id"]
    if (not isinstance(hardware, str) or hardware not in contract["compatible_hardware"] or
            hardware not in image["compatible_hardware"]):
        _fail("CAL_HARDWARE_MISMATCH", "hardware is incompatible")
    definitions = contract["parameters"]
    values = calibration["parameters"]
    if not isinstance(definitions, dict) or not definitions or not isinstance(values, list):
        _fail("INVALID_PARAMETERS", "expected contract definitions and calibration values")
    for name, definition in definitions.items():
        _token(name)
        _keys(definition, {"unit", "minimum", "maximum"}, name)
        if not isinstance(definition["unit"], str) or not definition["unit"].strip():
            _fail("INVALID_CONTRACT", f"{name} has no unit")
        if _number(definition["minimum"]) > _number(definition["maximum"]):
            _fail("INVALID_CONTRACT", f"{name} has reversed bounds")
    observed: set[str] = set()
    for entry in values:
        _keys(entry, {"name", "value", "unit"}, "parameter value")
        name = _token(entry["name"])
        if name in observed:
            _fail("CAL_DUPLICATE_PARAMETER", name)
        observed.add(name)
        if name not in definitions:
            _fail("CAL_UNKNOWN_PARAMETER", name)
        definition = definitions[name]
        if entry["unit"] != definition["unit"]:
            _fail("CAL_UNIT_MISMATCH", name)
        value = _number(entry["value"])
        if not definition["minimum"] <= value <= definition["maximum"]:
            _fail("CAL_VALUE_OUT_OF_RANGE", name)
    if observed != set(definitions):
        _fail("CAL_MISSING_PARAMETER", ", ".join(sorted(set(definitions) - observed)))
    return {"calibration_id": calibration["calibration_id"],
            "contract_id": contract["contract_id"], "ecu_id": calibration["ecu_id"],
            "software_version": calibration["software_version"], "parameter_count": len(observed)}


def validate_calibration(manifest_path: Path, contract_path: Path, calibration_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    dependency_order(manifest.images)
    software = {i.ecu_id: {"version": i.version, "compatible_hardware": i.compatible_hardware}
                for i in manifest.images}
    return _validate(_read(contract_path), _read(calibration_path), software)


def _encode(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _archive_name(name: Any) -> str:
    if (not isinstance(name, str) or "\\" in name or
            PurePosixPath(name).is_absolute() or
            any(p in {"", ".", ".."} for p in name.split("/"))):
        _fail("INVALID_ARCHIVE_PATH", repr(name))
    return name


def build_release(manifest_path: Path, contract_path: Path, calibration_path: Path,
                  output: Path) -> dict:
    manifest = load_manifest(manifest_path)
    order = dependency_order(manifest.images)
    contract, calibration = _read(contract_path), _read(calibration_path)
    software = []
    payloads = {"calibration/contract.json": _encode(contract),
                "calibration/values.json": _encode(calibration)}
    for image in manifest.images:
        ecu = _token(image.ecu_id)
        filename = _token(Path(image.file_name).name)
        name = f"software/{ecu}/{filename}"
        payloads[name] = image.payload
        software.append({"ecu_id": ecu, "version": image.version,
                         "compatible_hardware": list(image.compatible_hardware),
                         "depends_on": list(image.depends_on), "archive_path": name})
    summary = _validate(contract, calibration, {i["ecu_id"]: i for i in software})
    inventory = [{"path": name, "size": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest()}
                 for name, payload in sorted(payloads.items())]
    metadata = {"schema_version": 1, "campaign_id": manifest.campaign_id,
                "calibration_id": summary["calibration_id"],
                "update_order": [i.ecu_id for i in order],
                "software": sorted(software, key=lambda i: i["ecu_id"]), "artifacts": inventory}
    payloads["release.json"] = _encode(metadata)
    if sum(map(len, payloads.values())) > MAX_BUNDLE_BYTES:
        _fail("BUNDLE_TOO_LARGE", "uncompressed limit exceeded")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".release-", dir=output.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, payload in sorted(payloads.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload)
        verify_release(Path(temporary))
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {**summary, "bundle_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "bundle_bytes": output.stat().st_size, "artifact_count": len(inventory)}


def verify_release(bundle: Path) -> dict:
    try:
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or len(names) > 64:
                _fail("INVALID_BUNDLE", "duplicate names or excessive member count")
            if sum(i.file_size for i in infos) > MAX_BUNDLE_BYTES:
                _fail("BUNDLE_TOO_LARGE", "uncompressed limit exceeded")
            for name in names:
                _archive_name(name)
            if "release.json" not in names:
                _fail("INVALID_BUNDLE", "release.json is missing")
            metadata = _json(archive.read("release.json"))
            _keys(metadata, {"schema_version", "campaign_id", "calibration_id", "update_order",
                             "software", "artifacts"}, "release metadata")
            if type(metadata["schema_version"]) is not int or metadata["schema_version"] != 1:
                _fail("UNSUPPORTED_SCHEMA", "release schema_version must be integer 1")
            if not isinstance(metadata["campaign_id"], str):
                _fail("INVALID_BUNDLE", "campaign identity must be a string")
            _token(metadata["calibration_id"])
            inventory = metadata["artifacts"]
            if not isinstance(inventory, list):
                _fail("INVALID_BUNDLE", "artifacts must be a list")
            inventoried = []
            for item in inventory:
                _keys(item, {"path", "size", "sha256"}, "inventory entry")
                name = _archive_name(item["path"])
                if name == "release.json" or name not in names:
                    _fail("INVALID_BUNDLE", "inventory references an invalid member")
                payload = archive.read(name)
                if (type(item["size"]) is not int or len(payload) != item["size"] or
                        hashlib.sha256(payload).hexdigest() != item["sha256"]):
                    _fail("ARTIFACT_INTEGRITY_MISMATCH", name)
                inventoried.append(name)
            if len(inventoried) != len(set(inventoried)) or set(names) != {*inventoried, "release.json"}:
                _fail("INVALID_BUNDLE", "inventory does not match archive contents")
            software_raw = metadata["software"]
            if not isinstance(software_raw, list) or not software_raw:
                _fail("INVALID_BUNDLE", "software must be a nonempty list")
            software = {}
            for image in software_raw:
                _keys(image, {"ecu_id", "version", "compatible_hardware", "depends_on",
                              "archive_path"}, "software entry")
                ecu = _token(image["ecu_id"])
                archive_path = _archive_name(image["archive_path"])
                if (ecu in software or archive_path not in inventoried or
                        not archive_path.startswith(f"software/{ecu}/")):
                    _fail("INVALID_BUNDLE", "duplicate ECU or missing software artifact")
                if (not isinstance(image["compatible_hardware"], list) or not image["compatible_hardware"] or
                        any(not isinstance(h, str) for h in image["compatible_hardware"]) or
                        not isinstance(image["depends_on"], list) or
                        any(not isinstance(d, str) for d in image["depends_on"])):
                    _fail("INVALID_BUNDLE", "invalid software compatibility fields")
                if not isinstance(image["version"], str):
                    _fail("INVALID_BUNDLE", "software version must be a string")
                version_tuple(image["version"])
                software[ecu] = image
            expected_names = {i["archive_path"] for i in software.values()}
            expected_names.update({"calibration/contract.json", "calibration/values.json"})
            if expected_names != set(inventoried):
                _fail("INVALID_BUNDLE", "unexpected or missing artifact")
            order = metadata["update_order"]
            if (not isinstance(order, list) or any(not isinstance(v, str) for v in order) or
                    len(order) != len(software) or set(order) != set(software)):
                _fail("INVALID_BUNDLE", "update order must name each ECU once")
            for ecu, image in software.items():
                if any(d not in software or order.index(d) >= order.index(ecu) for d in image["depends_on"]):
                    _fail("INVALID_BUNDLE", "software dependency order is invalid")
            result = _validate(_json(archive.read("calibration/contract.json")),
                               _json(archive.read("calibration/values.json")), software)
            if metadata["calibration_id"] != result["calibration_id"]:
                _fail("INVALID_BUNDLE", "calibration identity mismatch")
            return {**result, "artifact_count": len(inventoried), "verified": True}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise FormatError(f"BUNDLE_UNREADABLE: {exc}") from exc
