# Vehicle Software Download System Test Harness

[![CI](https://github.com/pthanureddy/vehicle-software-download-system-test-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/pthanureddy/vehicle-software-download-system-test-harness/actions/workflows/ci.yml)

A requirements-based Python harness for testing complete-system software-download (SWDL) behavior across simulated vehicle ECUs. It validates software packages and compatibility, executes dependency-ordered updates over an in-memory Ethernet-style transport, models dual-bank bootloader activation and rollback, and produces reviewable test evidence.

The reference plan covers 10 higher-level system scenarios and 10 requirements across a synthetic Vehicle Gateway, Core Compute Module, and Infotainment Head Unit. The verified reference run performed 77 network attempts, 3 retries, and 4 rollback operations with 10/10 scenarios passing.

## What it demonstrates

- Python test automation for complete-system SWDL scenarios
- SHA-256 package integrity, declared size, path, hardware ID, bootloader version, storage, battery-voltage, and ignition-state checks
- Dependency ordering across three ECUs in a distributed update topology
- Chunked transfer with deterministic packet loss, retry/resume, corruption, and retry-budget exhaustion
- Dual-bank bootloader state, activation, post-install health checks, and transactional rollback
- Already-current ECU handling and structured failure codes
- Requirement-linked JSON test plans plus JSON, Markdown, and CSV results
- 63 automated unit, integration, system-runner, reporting, and CLI tests
- GitHub Actions on Ubuntu and Windows with Python 3.11 and 3.12

## Evidence boundary

This is a software-in-the-loop portfolio project with synthetic firmware files, vehicle state, and ECU definitions. It does **not** connect to a physical vehicle, test rig, bootloader, CAN/Ethernet network, VIDA, VCATS, CANoe, Canalyzer, Wireshark, or Volvo system. “Ethernet-style” means an in-memory chunk transport with controlled failure injection, not a real protocol implementation. See [docs/evidence-boundary.md](docs/evidence-boundary.md).

## Quick start

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Validate the manifest, package hashes, and ECU dependency graph:

```bash
vehicle-swdl validate-manifest --manifest examples/manifest.json
```

Execute the higher-level SWDL system test plan:

```bash
vehicle-swdl run \
  --vehicle examples/vehicle.json \
  --manifest examples/manifest.json \
  --plan examples/system_test_plan.json \
  --output-dir artifacts/system-tests
```

Expected summary:

```json
{
  "case_count": 10,
  "failed_case_count": 0,
  "network_attempt_count": 77,
  "network_retry_count": 3,
  "passed_case_count": 10,
  "requirement_count": 10,
  "rollback_count": 4
}
```

## Repository map

```text
vehicle_swdl/         package models, topology, ECU state, network, orchestration, reports
tests/                unit, integration, system-runner, report, and CLI regression tests
examples/             synthetic firmware packages, vehicle, manifest, and system test plan
docs/                 architecture, requirements, strategy, and evidence boundary
artifacts/             generated reference results
.github/workflows/     Ubuntu/Windows, Python 3.11/3.12 CI
```

## Cross-platform package integrity

The files under `examples/packages/` are synthetic firmware fixtures whose
declared byte counts and SHA-256 digests are part of the manifest contract.
Although their sample contents are human-readable, they must be checked out as
binary data. The repository's `.gitattributes` marks `*.bin` as binary so Git
does not convert LF bytes to CRLF on Windows. Both Windows and Ubuntu CI jobs
validate the manifest before executing the reference system test plan.

## Failure handling

- Input and manifest errors return CLI exit code 2.
- Any expectation mismatch in the system test plan returns exit code 1 and remains in the reports.
- Runtime download failures use stable codes such as `IMAGE_HASH_MISMATCH`, `LOW_BATTERY_VOLTAGE`, `BOOTLOADER_TOO_OLD`, `NETWORK_RETRY_EXHAUSTED`, and `POST_INSTALL_HEALTH_CHECK_FAILED`.
- Activated ECUs roll back in reverse update order when a later image or health check fails.

## Documentation

- [Architecture](docs/architecture.md)
- [Requirements and test plan](docs/requirements-and-test-plan.md)
- [System test strategy](docs/system-test-strategy.md)
- [Evidence boundary](docs/evidence-boundary.md)

## License

MIT
