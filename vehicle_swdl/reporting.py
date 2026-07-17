from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import json


def write_system_test_report(report: dict[str, Any], output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "swdl_system_test_results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = report["summary"]
    lines = [
        "# Software Download System Test Results",
        "",
        f"- Plan: {report['plan_id']}",
        f"- Cases: {summary['case_count']}",
        f"- Passed: {summary['passed_case_count']}",
        f"- Failed: {summary['failed_case_count']}",
        f"- Requirements: {summary['requirement_count']}",
        f"- Network attempts: {summary['network_attempt_count']}",
        f"- Network retries: {summary['network_retry_count']}",
        f"- Rollbacks: {summary['rollback_count']}",
        "",
    ]
    for case in report["cases"]:
        result = case["campaign_result"]
        lines.extend(
            [
                f"## {case['case_id']} / {case['requirement_id']} - {'PASS' if case['passed'] else 'FAIL'}",
                "",
                case["name"],
                "",
                f"- Campaign status: {result['status']}",
                f"- Failure code: {result['failure_code'] or 'none'}",
                f"- Updated ECUs: {result['updated_ecu_count']}",
                f"- Skipped ECUs: {result['skipped_ecu_count']}",
                f"- Network attempts/retries: {result['network_attempt_count']}/{result['network_retry_count']}",
                f"- Rollbacks: {result['rollback_count']}",
            ]
        )
        lines.extend(f"- Mismatch: {item}" for item in case["mismatches"])
        lines.append("")
    (destination / "swdl_system_test_results.md").write_text("\n".join(lines), encoding="utf-8")

    with (destination / "swdl_system_test_results.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case_id",
                "requirement_id",
                "passed",
                "campaign_status",
                "failure_code",
                "updated_ecus",
                "network_attempts",
                "network_retries",
                "rollbacks",
            ]
        )
        for case in report["cases"]:
            result = case["campaign_result"]
            writer.writerow(
                [
                    case["case_id"],
                    case["requirement_id"],
                    case["passed"],
                    result["status"],
                    result["failure_code"],
                    result["updated_ecu_count"],
                    result["network_attempt_count"],
                    result["network_retry_count"],
                    result["rollback_count"],
                ]
            )
