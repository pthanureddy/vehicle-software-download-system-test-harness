from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .models import FaultPlan, FormatError, VehicleDefinition, load_manifest, read_json
from .orchestrator import run_campaign


def _apply_overrides(vehicle: dict[str, Any], overrides: dict[str, Any]) -> None:
    for field in ("battery_voltage", "ignition_state"):
        if field in overrides:
            vehicle[field] = overrides[field]
    ecu_by_id = {str(ecu["ecu_id"]): ecu for ecu in vehicle.get("ecus", [])}
    field_maps = {
        "hardware_id": "ecu_hardware_id",
        "bootloader_version": "ecu_bootloader_version",
        "storage_capacity": "ecu_storage_capacity",
    }
    for ecu_field, override_field in field_maps.items():
        raw = overrides.get(override_field, {})
        if not isinstance(raw, dict):
            raise FormatError(f"Scenario override {override_field!r} must be an object")
        for ecu_id, value in raw.items():
            if str(ecu_id) not in ecu_by_id:
                raise FormatError(f"Scenario override refers to unknown ECU {ecu_id!r}")
            ecu_by_id[str(ecu_id)][ecu_field] = value
    versions = overrides.get("ecu_active_version", {})
    if not isinstance(versions, dict):
        raise FormatError("Scenario override 'ecu_active_version' must be an object")
    for ecu_id, value in versions.items():
        ecu = ecu_by_id.get(str(ecu_id))
        if ecu is None:
            raise FormatError(f"Scenario override refers to unknown ECU {ecu_id!r}")
        ecu["slot_versions"][ecu["active_slot"]] = value


def _matches_expectation(result: dict[str, Any], expected: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    for field in ("status", "failure_code", "updated_ecu_count", "skipped_ecu_count", "rollback_count"):
        if field in expected and result.get(field) != expected[field]:
            mismatches.append(f"{field}: expected {expected[field]!r}, found {result.get(field)!r}")
    expected_versions = expected.get("versions", {})
    if not isinstance(expected_versions, dict):
        raise FormatError("Scenario expected versions must be an object")
    for ecu_id, version in expected_versions.items():
        actual = result["after_versions"].get(ecu_id)
        if actual != version:
            mismatches.append(f"version {ecu_id}: expected {version!r}, found {actual!r}")
    if expected.get("minimum_retry_count") is not None:
        minimum = int(expected["minimum_retry_count"])
        if int(result["network_retry_count"]) < minimum:
            mismatches.append(
                f"network_retry_count: expected at least {minimum}, found {result['network_retry_count']}"
            )
    return not mismatches, mismatches


def run_system_test_plan(
    vehicle_path: str | Path,
    manifest_path: str | Path,
    plan_path: str | Path,
) -> dict[str, Any]:
    vehicle_document = read_json(vehicle_path)
    manifest = load_manifest(manifest_path)
    plan = read_json(plan_path)
    scenarios = plan.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise FormatError("System test plan scenarios must be a non-empty list")
    case_results: list[dict[str, Any]] = []
    for scenario in scenarios:
        required = {"id", "requirement_id", "name", "expected"}
        missing = sorted(required - scenario.keys())
        if missing:
            raise FormatError(f"Scenario is missing fields: {', '.join(missing)}")
        scenario_vehicle = deepcopy(vehicle_document)
        _apply_overrides(scenario_vehicle, scenario.get("overrides", {}))
        vehicle = VehicleDefinition.from_mapping(scenario_vehicle)
        result = run_campaign(
            vehicle,
            manifest,
            faults=FaultPlan.from_mapping(scenario.get("faults")),
            chunk_size=int(scenario.get("chunk_size", 8)),
            max_attempts=int(scenario.get("max_attempts", 3)),
        )
        passed, mismatches = _matches_expectation(result, scenario["expected"])
        case_results.append(
            {
                "case_id": str(scenario["id"]),
                "requirement_id": str(scenario["requirement_id"]),
                "name": str(scenario["name"]),
                "passed": passed,
                "mismatches": mismatches,
                "campaign_result": result,
            }
        )
    passed_count = sum(case["passed"] for case in case_results)
    requirements = sorted({case["requirement_id"] for case in case_results})
    return {
        "plan_id": str(plan.get("plan_id", "unnamed")),
        "summary": {
            "case_count": len(case_results),
            "passed_case_count": passed_count,
            "failed_case_count": len(case_results) - passed_count,
            "requirement_count": len(requirements),
            "network_attempt_count": sum(
                case["campaign_result"]["network_attempt_count"] for case in case_results
            ),
            "network_retry_count": sum(
                case["campaign_result"]["network_retry_count"] for case in case_results
            ),
            "rollback_count": sum(case["campaign_result"]["rollback_count"] for case in case_results),
        },
        "requirements": requirements,
        "cases": case_results,
    }
