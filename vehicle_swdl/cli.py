from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from .models import FormatError, load_manifest
from .reporting import write_system_test_report
from .runner import run_system_test_plan
from .topology import dependency_order
from .calibration_release import build_release, validate_calibration, verify_release


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vehicle-swdl",
        description="Validate SWDL packages and run simulated complete-system update tests.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-manifest", help="Verify packages and ECU dependencies")
    validate.add_argument("--manifest", type=Path, required=True)
    run = commands.add_parser("run", help="Execute a requirements-based SWDL system test plan")
    run.add_argument("--vehicle", type=Path, required=True)
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    calibration = commands.add_parser("validate-calibration", help="Check calibration compatibility and parameter bounds")
    release = commands.add_parser("build-release", help="Build a reproducible software and calibration archive")
    for command in (calibration, release):
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--contract", type=Path, required=True)
        command.add_argument("--calibration", type=Path, required=True)
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--report", type=Path)
    verify = commands.add_parser("verify-release", help="Verify bundle inventory, integrity, and calibration contract")
    verify.add_argument("--bundle", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"validate-calibration", "build-release", "verify-release"}:
            if args.command == "validate-calibration":
                result = validate_calibration(args.manifest, args.contract, args.calibration)
            elif args.command == "build-release":
                result = build_release(args.manifest, args.contract, args.calibration, args.output)
                if args.report:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            else:
                result = verify_release(args.bundle)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "validate-manifest":
            manifest = load_manifest(args.manifest)
            order = dependency_order(manifest.images)
            print(
                json.dumps(
                    {
                        "campaign_id": manifest.campaign_id,
                        "image_count": len(manifest.images),
                        "update_order": [image.ecu_id for image in order],
                        "total_package_bytes": sum(image.size for image in manifest.images),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        report = run_system_test_plan(args.vehicle, args.manifest, args.plan)
        write_system_test_report(report, args.output_dir)
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        return int(bool(report["summary"]["failed_case_count"]))
    except (FormatError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
