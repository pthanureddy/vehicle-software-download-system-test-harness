# Calibration validation and artifact delivery

This extension checks a synthetic calibration against a separate parameter
contract and the software manifest, then packages firmware and calibration data
into one reproducible delivery artifact. It addresses early compatibility and
data-quality failures before a simulated software-download campaign.

## Inputs and behavior

- `examples/manifest.json` contains firmware bytes, sizes, SHA-256 digests,
  compatible hardware and ECU dependencies. Existing SWDL validation is reused.
- `examples/calibration_contract.json` declares one target ECU, exact compatible
  software versions, compatible hardware, and required parameter units and bounds.
- `examples/calibration.json` contains the selected target and parameter values.
  Values cannot redefine their permitted bounds; the separate contract owns them.

Validation rejects duplicate JSON keys or parameters, missing or unknown values,
non-finite numbers, booleans used as numbers, wrong units, out-of-range values,
and contract/software/hardware mismatches. Units must match exactly; there is no
automatic conversion. Software versions also match exactly, without range syntax.

```powershell
vehicle-swdl validate-calibration --manifest examples/manifest.json --contract examples/calibration_contract.json --calibration examples/calibration.json
vehicle-swdl build-release --manifest examples/manifest.json --contract examples/calibration_contract.json --calibration examples/calibration.json --output artifacts/ci-release/software-calibration.zip --report artifacts/ci-release/report.json
vehicle-swdl verify-release --bundle artifacts/ci-release/software-calibration.zip
```

All commands return JSON on success. Invalid input or a bad archive returns exit
code 2 with a diagnostic on stderr, such as `CAL_SOFTWARE_MISMATCH`,
`CAL_UNIT_MISMATCH`, `CAL_VALUE_OUT_OF_RANGE`, or `ARTIFACT_INTEGRITY_MISMATCH`.

## Architecture and release format

`calibration_release.py` validates typed inputs, reuses manifest integrity and
topology checks, canonicalizes JSON, and writes the bundle atomically. The CLI
does argument parsing and optional report writing. It does not alter ECU state.

The ZIP contains `release.json`, `calibration/contract.json`,
`calibration/values.json`, and each firmware file under its ECU directory.
`release.json` records versions, dependency order, sizes and SHA-256 digests.
Verification reads members without extracting them, checks the exact inventory
and dependency order, then revalidates calibration semantics. There are limits
of 64 archive members and 16 MiB total uncompressed content.

For identical input bytes, fixed ZIP metadata, sorted file paths, uncompressed
members and sorted JSON object keys produce byte-identical archives. Array order
is preserved. Firmware fixtures remain binary in Git to prevent newline changes.

The GitHub Actions matrix validates the contract and bundle on Windows and Linux
with Python 3.11 and 3.12. A delivery job runs only after those checks pass, builds
the Python wheel and validated bundle, and uploads both with the digest report.
This is continuous delivery of downloadable artifacts, not deployment to a vehicle.

## Requirements and verification

| Requirement | Evidence |
| --- | --- |
| CAL-001 Bind values to software, ECU and hardware | Compatibility and mismatch tests |
| CAL-002 Enforce units, required values and finite bounds | Parameterized rejection and boundary tests |
| REL-001 Detect artifact corruption and invalid inventories | Tampering and archive-path tests |
| REL-002 Produce deterministic artifacts | Byte-for-byte rebuild test |
| REL-003 Preserve a valid release when validation fails | Atomic-output regression test |
| REL-004 Publish only after cross-platform checks | `deliver-artifacts` needs the complete CI test matrix |

Run `python -m pytest` for the complete suite. Tests also update an archive's
inventory hash after changing a calibration value, showing that semantic checks
still reject a bad unit even when byte-integrity checks pass.

## Limits and trade-offs

The numbers and units are invented engineering fixtures, not validated vehicle
calibration values. No ASAM A2L, XCP, UDS flashing, real ECU, or manufacturer tool
is implemented. A bundle does not apply calibration values to the simulated
controller or prove closed-loop control behavior. ZIP storage favors portable
reproducibility over compression. Hashes detect corruption but do not establish
authenticity; there are no signing keys, trusted signatures, secure boot, or
production release approvals. A real system would need those controls plus
versioned contracts reviewed by domain engineers and hardware verification.
