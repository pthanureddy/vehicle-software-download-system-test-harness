from __future__ import annotations

from typing import Any

from .ecu import DownloadFailure, ECUSimulator
from .models import DownloadManifest, FaultPlan, SoftwareImage, VehicleDefinition, version_at_least
from .network import EthernetLoopback
from .topology import dependency_order


def _failure(status: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "failure_code": code, "message": message}
    result.update(extra)
    return result


def _versions(ecus: dict[str, ECUSimulator]) -> dict[str, str]:
    return {ecu_id: ecu.active_version for ecu_id, ecu in sorted(ecus.items())}


def _preflight(
    vehicle: VehicleDefinition,
    ordered_images: list[SoftwareImage],
    ecus: dict[str, ECUSimulator],
) -> dict[str, Any] | None:
    if vehicle.ignition_state != "service":
        return _failure(
            "BLOCKED",
            "INVALID_IGNITION_STATE",
            f"Ignition state must be 'service', found {vehicle.ignition_state!r}",
        )
    for image in ordered_images:
        ecu = ecus.get(image.ecu_id)
        if ecu is None:
            return _failure("BLOCKED", "ECU_NOT_FOUND", f"Vehicle has no ECU {image.ecu_id!r}")
        if vehicle.battery_voltage < image.minimum_battery_voltage:
            return _failure(
                "BLOCKED",
                "LOW_BATTERY_VOLTAGE",
                f"Battery {vehicle.battery_voltage:g} V is below {image.minimum_battery_voltage:g} V",
            )
        if ecu.hardware_id not in image.compatible_hardware:
            return _failure(
                "BLOCKED",
                "HARDWARE_INCOMPATIBLE",
                f"ECU {ecu.ecu_id} hardware {ecu.hardware_id!r} is not compatible",
            )
        if not version_at_least(ecu.bootloader_version, image.minimum_bootloader):
            return _failure(
                "BLOCKED",
                "BOOTLOADER_TOO_OLD",
                f"ECU {ecu.ecu_id} bootloader {ecu.bootloader_version} is below {image.minimum_bootloader}",
            )
        if ecu.storage_capacity < image.size:
            return _failure(
                "BLOCKED",
                "INSUFFICIENT_STORAGE",
                f"ECU {ecu.ecu_id} has {ecu.storage_capacity} bytes for a {image.size}-byte image",
            )
    return None


def run_campaign(
    vehicle: VehicleDefinition,
    manifest: DownloadManifest,
    *,
    faults: FaultPlan | None = None,
    chunk_size: int = 8,
    max_attempts: int = 3,
) -> dict[str, Any]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    ordered_images = dependency_order(manifest.images)
    ecus = {definition.ecu_id: ECUSimulator(definition) for definition in vehicle.ecus}
    before_versions = _versions(ecus)
    common = {
        "campaign_id": manifest.campaign_id,
        "vehicle_id": vehicle.vehicle_id,
        "before_versions": before_versions,
        "update_order": [image.ecu_id for image in ordered_images],
    }
    preflight = _preflight(vehicle, ordered_images, ecus)
    if preflight:
        return {
            **common,
            **preflight,
            "after_versions": _versions(ecus),
            "updated_ecu_count": 0,
            "skipped_ecu_count": 0,
            "rollback_count": 0,
            "network_attempt_count": 0,
            "network_retry_count": 0,
            "ecu_results": [],
            "network_trace": [],
        }

    fault_plan = faults or FaultPlan.from_mapping(None)
    network = EthernetLoopback(fault_plan)
    updated: list[ECUSimulator] = []
    ecu_results: list[dict[str, Any]] = []
    skipped_count = 0

    def fail(code: str, message: str, ecu_id: str) -> dict[str, Any]:
        rollback_count = sum(ecu.rollback() for ecu in reversed(updated))
        return {
            **common,
            "status": "FAILED",
            "failure_code": code,
            "message": message,
            "failed_ecu_id": ecu_id,
            "after_versions": _versions(ecus),
            "updated_ecu_count": 0,
            "skipped_ecu_count": skipped_count,
            "rollback_count": rollback_count,
            "network_attempt_count": len(network.trace),
            "network_retry_count": sum(int(item["attempt"]) > 1 for item in network.trace),
            "ecu_results": ecu_results,
            "network_trace": network.trace,
        }

    for image in ordered_images:
        ecu = ecus[image.ecu_id]
        previous_version = ecu.active_version
        if previous_version == image.version:
            skipped_count += 1
            ecu_results.append(
                {
                    "ecu_id": ecu.ecu_id,
                    "status": "SKIPPED_ALREADY_CURRENT",
                    "before_version": previous_version,
                    "after_version": ecu.active_version,
                    "chunk_count": 0,
                }
            )
            continue
        chunks = [
            image.payload[offset : offset + chunk_size]
            for offset in range(0, len(image.payload), chunk_size)
        ]
        ecu.begin(image, len(chunks))
        for index, chunk in enumerate(chunks):
            delivered: bytes | None = None
            for attempt in range(1, max_attempts + 1):
                delivered = network.transmit(ecu.ecu_id, index, chunk, attempt)
                if delivered is not None:
                    break
            if delivered is None:
                return fail(
                    "NETWORK_RETRY_EXHAUSTED",
                    f"ECU {ecu.ecu_id} chunk {index} was not delivered after {max_attempts} attempts",
                    ecu.ecu_id,
                )
            ecu.receive(index, delivered)
        try:
            staged_slot = ecu.finalize()
            ecu.activate()
        except DownloadFailure as exc:
            return fail(exc.code, str(exc), ecu.ecu_id)
        updated.append(ecu)
        if ecu.ecu_id in fault_plan.health_check_fail:
            return fail(
                "POST_INSTALL_HEALTH_CHECK_FAILED",
                f"ECU {ecu.ecu_id} failed the simulated post-install health check",
                ecu.ecu_id,
            )
        ecu_results.append(
            {
                "ecu_id": ecu.ecu_id,
                "status": "UPDATED",
                "before_version": previous_version,
                "after_version": ecu.active_version,
                "staged_slot": staged_slot,
                "chunk_count": len(chunks),
            }
        )

    for ecu in updated:
        ecu.commit()
    return {
        **common,
        "status": "COMPLETED",
        "failure_code": None,
        "message": "Software-download campaign completed",
        "after_versions": _versions(ecus),
        "updated_ecu_count": len(updated),
        "skipped_ecu_count": skipped_count,
        "rollback_count": 0,
        "network_attempt_count": len(network.trace),
        "network_retry_count": sum(int(item["attempt"]) > 1 for item in network.trace),
        "ecu_results": ecu_results,
        "network_trace": network.trace,
    }
