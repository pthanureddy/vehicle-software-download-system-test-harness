from dataclasses import replace

import pytest

from vehicle_swdl.models import FaultPlan
from vehicle_swdl.orchestrator import run_campaign


TARGET = {"gateway": "5.5.0", "ccm": "2.2.0", "infotainment": "9.4.0"}
ORIGINAL = {"gateway": "5.4.2", "ccm": "2.1.0", "infotainment": "9.3.1"}


def replace_ecu(vehicle, ecu_id, **changes):
    ecus = tuple(replace(ecu, **changes) if ecu.ecu_id == ecu_id else ecu for ecu in vehicle.ecus)
    return replace(vehicle, ecus=ecus)


def test_complete_campaign_updates_ecus_in_dependency_order(vehicle, manifest):
    result = run_campaign(vehicle, manifest)
    assert result["status"] == "COMPLETED"
    assert result["after_versions"] == TARGET
    assert result["update_order"] == ["gateway", "ccm", "infotainment"]
    assert result["updated_ecu_count"] == 3
    assert result["network_attempt_count"] == 20


def test_transient_loss_is_retried_without_restarting_campaign(vehicle, manifest):
    result = run_campaign(
        vehicle,
        manifest,
        faults=FaultPlan.from_mapping({"drop_once": {"gateway": [1]}}),
    )
    assert result["status"] == "COMPLETED"
    assert result["network_retry_count"] == 1
    assert result["network_attempt_count"] == 21


def test_corrupted_image_rolls_back_prior_ecu(vehicle, manifest):
    result = run_campaign(
        vehicle,
        manifest,
        faults=FaultPlan.from_mapping({"corrupt": {"ccm": [0]}}),
    )
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "IMAGE_HASH_MISMATCH"
    assert result["rollback_count"] == 1
    assert result["after_versions"] == ORIGINAL


def test_post_install_health_failure_rolls_back_complete_campaign(vehicle, manifest):
    result = run_campaign(
        vehicle,
        manifest,
        faults=FaultPlan.from_mapping({"health_check_fail": ["infotainment"]}),
    )
    assert result["failure_code"] == "POST_INSTALL_HEALTH_CHECK_FAILED"
    assert result["rollback_count"] == 3
    assert result["after_versions"] == ORIGINAL


def test_permanent_loss_exhausts_retry_budget(vehicle, manifest):
    result = run_campaign(
        vehicle,
        manifest,
        faults=FaultPlan.from_mapping({"drop_always": {"gateway": [0]}}),
    )
    assert result["failure_code"] == "NETWORK_RETRY_EXHAUSTED"
    assert result["network_attempt_count"] == 3
    assert result["after_versions"] == ORIGINAL


def test_low_battery_blocks_before_network_activity(vehicle, manifest):
    result = run_campaign(replace(vehicle, battery_voltage=11.9), manifest)
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "LOW_BATTERY_VOLTAGE"
    assert result["network_attempt_count"] == 0


def test_invalid_ignition_blocks_campaign(vehicle, manifest):
    result = run_campaign(replace(vehicle, ignition_state="drive"), manifest)
    assert result["failure_code"] == "INVALID_IGNITION_STATE"


def test_incompatible_hardware_blocks_campaign(vehicle, manifest):
    result = run_campaign(replace_ecu(vehicle, "ccm", hardware_id="CCM-HW-01"), manifest)
    assert result["failure_code"] == "HARDWARE_INCOMPATIBLE"


def test_old_bootloader_blocks_campaign(vehicle, manifest):
    result = run_campaign(replace_ecu(vehicle, "gateway", bootloader_version="1.9.0"), manifest)
    assert result["failure_code"] == "BOOTLOADER_TOO_OLD"


def test_insufficient_storage_blocks_campaign(vehicle, manifest):
    result = run_campaign(replace_ecu(vehicle, "gateway", storage_capacity=10), manifest)
    assert result["failure_code"] == "INSUFFICIENT_STORAGE"


def test_missing_ecu_blocks_campaign(vehicle, manifest):
    result = run_campaign(replace(vehicle, ecus=vehicle.ecus[1:]), manifest)
    assert result["failure_code"] == "ECU_NOT_FOUND"


def test_current_versions_are_skipped(vehicle, manifest):
    current = vehicle
    for ecu_id, version in TARGET.items():
        ecu = next(item for item in current.ecus if item.ecu_id == ecu_id)
        slots = dict(ecu.slot_versions)
        slots[ecu.active_slot] = version
        current = replace_ecu(current, ecu_id, slot_versions=slots)
    result = run_campaign(current, manifest)
    assert result["status"] == "COMPLETED"
    assert result["updated_ecu_count"] == 0
    assert result["skipped_ecu_count"] == 3
    assert result["network_attempt_count"] == 0


@pytest.mark.parametrize(("field", "value"), [("chunk_size", 0), ("max_attempts", 0)])
def test_invalid_runner_limits_are_rejected(vehicle, manifest, field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError, match="positive"):
        run_campaign(vehicle, manifest, **kwargs)
