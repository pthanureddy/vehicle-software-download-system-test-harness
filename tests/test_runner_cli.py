from copy import deepcopy
import json

from vehicle_swdl.cli import main
from vehicle_swdl.reporting import write_system_test_report
from vehicle_swdl.runner import run_system_test_plan


def test_reference_system_plan_passes_all_cases(example_dir):
    report = run_system_test_plan(
        example_dir / "vehicle.json",
        example_dir / "manifest.json",
        example_dir / "system_test_plan.json",
    )
    assert report["summary"]["case_count"] == 10
    assert report["summary"]["passed_case_count"] == 10
    assert report["summary"]["requirement_count"] == 10
    assert report["summary"]["network_retry_count"] >= 1
    assert report["summary"]["rollback_count"] == 4


def test_report_writer_creates_json_markdown_and_csv(example_dir, tmp_path):
    report = run_system_test_plan(
        example_dir / "vehicle.json",
        example_dir / "manifest.json",
        example_dir / "system_test_plan.json",
    )
    write_system_test_report(report, tmp_path)
    assert (tmp_path / "swdl_system_test_results.json").exists()
    assert "SWDL-SYS-001" in (tmp_path / "swdl_system_test_results.md").read_text(encoding="utf-8")
    assert "requirement_id" in (tmp_path / "swdl_system_test_results.csv").read_text(encoding="utf-8")


def test_validate_manifest_cli_reports_order(example_dir, capsys):
    exit_code = main(["validate-manifest", "--manifest", str(example_dir / "manifest.json")])
    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["image_count"] == 3
    assert output["update_order"] == ["gateway", "ccm", "infotainment"]
    assert output["total_package_bytes"] == 151


def test_run_cli_generates_reports(example_dir, tmp_path, capsys):
    exit_code = main(
        [
            "run",
            "--vehicle",
            str(example_dir / "vehicle.json"),
            "--manifest",
            str(example_dir / "manifest.json"),
            "--plan",
            str(example_dir / "system_test_plan.json"),
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["failed_case_count"] == 0
    assert (tmp_path / "swdl_system_test_results.json").exists()


def test_run_cli_returns_one_when_expected_result_mismatches(example_dir, tmp_path, capsys):
    plan = json.loads((example_dir / "system_test_plan.json").read_text(encoding="utf-8"))
    plan["scenarios"] = [deepcopy(plan["scenarios"][0])]
    plan["scenarios"][0]["expected"]["updated_ecu_count"] = 99
    plan_path = tmp_path / "failing-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    exit_code = main(
        [
            "run",
            "--vehicle",
            str(example_dir / "vehicle.json"),
            "--manifest",
            str(example_dir / "manifest.json"),
            "--plan",
            str(plan_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["failed_case_count"] == 1


def test_cli_returns_two_for_missing_manifest(tmp_path, capsys):
    exit_code = main(["validate-manifest", "--manifest", str(tmp_path / "missing.json")])
    assert exit_code == 2
    assert "error:" in capsys.readouterr().err
