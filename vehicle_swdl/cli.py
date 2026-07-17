from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from .models import FormatError, load_manifest
from .reporting import write_system_test_report
from .runner import run_system_test_plan
from .topology import dependency_order


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
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
    except (FormatError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
