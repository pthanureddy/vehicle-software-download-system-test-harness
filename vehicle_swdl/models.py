from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re


class FormatError(ValueError):
    """Raised when a SWDL input document is incomplete or inconsistent."""


_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")


def version_tuple(value: str) -> tuple[int, ...]:
    text = str(value)
    if not _VERSION.fullmatch(text):
        raise FormatError(f"Invalid dotted numeric version: {text!r}")
    return tuple(int(part) for part in text.split("."))


def version_at_least(actual: str, minimum: str) -> bool:
    actual_parts = version_tuple(actual)
    minimum_parts = version_tuple(minimum)
    width = max(len(actual_parts), len(minimum_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= minimum_parts + (0,) * (
        width - len(minimum_parts)
    )


@dataclass(frozen=True)
class SoftwareImage:
    ecu_id: str
    version: str
    file_name: str
    payload: bytes
    sha256: str
    size: int
    compatible_hardware: tuple[str, ...]
    minimum_bootloader: str
    depends_on: tuple[str, ...]
    minimum_battery_voltage: float

    @classmethod
    def from_mapping(cls, data: dict[str, Any], base_dir: Path) -> "SoftwareImage":
        required = {
            "ecu_id",
            "version",
            "file",
            "sha256",
            "size",
            "compatible_hardware",
            "minimum_bootloader",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise FormatError(f"Software image is missing fields: {', '.join(missing)}")
        file_name = str(data["file"])
        path = (base_dir / file_name).resolve()
        try:
            path.relative_to(base_dir.resolve())
        except ValueError as exc:
            raise FormatError(f"Package path escapes the manifest directory: {file_name}") from exc
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise FormatError(f"Could not read package {file_name!r}: {exc}") from exc
        expected_size = int(data["size"])
        expected_hash = str(data["sha256"]).lower()
        actual_hash = hashlib.sha256(payload).hexdigest()
        if len(payload) != expected_size:
            raise FormatError(
                f"Package {file_name!r} size mismatch: expected {expected_size}, found {len(payload)}"
            )
        if actual_hash != expected_hash:
            raise FormatError(f"Package {file_name!r} SHA-256 mismatch")
        hardware = data["compatible_hardware"]
        if not isinstance(hardware, list) or not hardware:
            raise FormatError("compatible_hardware must be a non-empty list")
        version_tuple(str(data["version"]))
        version_tuple(str(data["minimum_bootloader"]))
        return cls(
            ecu_id=str(data["ecu_id"]),
            version=str(data["version"]),
            file_name=file_name,
            payload=payload,
            sha256=expected_hash,
            size=expected_size,
            compatible_hardware=tuple(str(item) for item in hardware),
            minimum_bootloader=str(data["minimum_bootloader"]),
            depends_on=tuple(str(item) for item in data.get("depends_on", [])),
            minimum_battery_voltage=float(data.get("minimum_battery_voltage", 12.0)),
        )


@dataclass(frozen=True)
class DownloadManifest:
    campaign_id: str
    images: tuple[SoftwareImage, ...]


@dataclass(frozen=True)
class ECUDefinition:
    ecu_id: str
    name: str
    hardware_id: str
    bootloader_version: str
    storage_capacity: int
    active_slot: str
    slot_versions: dict[str, str | None]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ECUDefinition":
        required = {
            "ecu_id",
            "name",
            "hardware_id",
            "bootloader_version",
            "storage_capacity",
            "active_slot",
            "slot_versions",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise FormatError(f"ECU is missing fields: {', '.join(missing)}")
        slots = data["slot_versions"]
        if not isinstance(slots, dict) or set(slots) != {"A", "B"}:
            raise FormatError("slot_versions must define exactly A and B")
        active = str(data["active_slot"])
        if active not in slots or slots[active] is None:
            raise FormatError("active_slot must refer to a populated slot")
        version_tuple(str(data["bootloader_version"]))
        for value in slots.values():
            if value is not None:
                version_tuple(str(value))
        capacity = int(data["storage_capacity"])
        if capacity <= 0:
            raise FormatError("storage_capacity must be positive")
        return cls(
            ecu_id=str(data["ecu_id"]),
            name=str(data["name"]),
            hardware_id=str(data["hardware_id"]),
            bootloader_version=str(data["bootloader_version"]),
            storage_capacity=capacity,
            active_slot=active,
            slot_versions={key: None if value is None else str(value) for key, value in slots.items()},
        )


@dataclass(frozen=True)
class VehicleDefinition:
    vehicle_id: str
    battery_voltage: float
    ignition_state: str
    ecus: tuple[ECUDefinition, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "VehicleDefinition":
        required = {"vehicle_id", "battery_voltage", "ignition_state", "ecus"}
        missing = sorted(required - data.keys())
        if missing:
            raise FormatError(f"Vehicle is missing fields: {', '.join(missing)}")
        ecus_raw = data["ecus"]
        if not isinstance(ecus_raw, list) or not ecus_raw:
            raise FormatError("Vehicle ecus must be a non-empty list")
        ecus = tuple(ECUDefinition.from_mapping(item) for item in ecus_raw)
        ecu_ids = [ecu.ecu_id for ecu in ecus]
        if len(ecu_ids) != len(set(ecu_ids)):
            raise FormatError("Vehicle ECU ids must be unique")
        voltage = float(data["battery_voltage"])
        if voltage <= 0:
            raise FormatError("battery_voltage must be positive")
        return cls(
            vehicle_id=str(data["vehicle_id"]),
            battery_voltage=voltage,
            ignition_state=str(data["ignition_state"]),
            ecus=ecus,
        )


@dataclass(frozen=True)
class FaultPlan:
    drop_once: dict[str, tuple[int, ...]]
    drop_always: dict[str, tuple[int, ...]]
    corrupt: dict[str, tuple[int, ...]]
    health_check_fail: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "FaultPlan":
        source = data or {}

        def index_map(name: str) -> dict[str, tuple[int, ...]]:
            raw = source.get(name, {})
            if not isinstance(raw, dict):
                raise FormatError(f"Fault field {name!r} must be an object")
            parsed: dict[str, tuple[int, ...]] = {}
            for ecu_id, indices in raw.items():
                if not isinstance(indices, list) or any(int(index) < 0 for index in indices):
                    raise FormatError(f"Fault indices for {ecu_id!r} must be non-negative")
                parsed[str(ecu_id)] = tuple(int(index) for index in indices)
            return parsed

        health = source.get("health_check_fail", [])
        if not isinstance(health, list):
            raise FormatError("health_check_fail must be a list")
        return cls(
            drop_once=index_map("drop_once"),
            drop_always=index_map("drop_always"),
            corrupt=index_map("corrupt"),
            health_check_fail=tuple(str(item) for item in health),
        )


def read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormatError(f"Could not read JSON document {source}: {exc}") from exc
    if not isinstance(document, dict):
        raise FormatError(f"JSON document {source} must contain an object")
    return document


def load_manifest(path: str | Path) -> DownloadManifest:
    source = Path(path)
    document = read_json(source)
    images_raw = document.get("images")
    if not isinstance(images_raw, list) or not images_raw:
        raise FormatError("Manifest images must be a non-empty list")
    images = tuple(SoftwareImage.from_mapping(item, source.parent) for item in images_raw)
    ecu_ids = [image.ecu_id for image in images]
    if len(ecu_ids) != len(set(ecu_ids)):
        raise FormatError("Manifest can contain only one image per ECU")
    return DownloadManifest(campaign_id=str(document.get("campaign_id", "unnamed")), images=images)


def load_vehicle(path: str | Path) -> VehicleDefinition:
    return VehicleDefinition.from_mapping(read_json(path))
