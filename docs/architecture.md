# Architecture

## Execution flow

1. `models.py` loads and validates the vehicle, manifest, package files, versions, and fault plan.
2. `topology.py` validates ECU dependencies and calculates a stable prerequisite-first update order.
3. `orchestrator.py` evaluates vehicle-wide preconditions before the first transfer.
4. `network.py` delivers fixed-size chunks through an in-memory Ethernet-style seam and records every attempt.
5. `ecu.py` reassembles the image, verifies its SHA-256 digest, stages it in the inactive slot, activates it, and supports rollback.
6. `runner.py` creates a fresh vehicle state per scenario, applies controlled overrides/faults, executes the campaign, and compares actual results with declared expectations.
7. `reporting.py` emits JSON, Markdown, and CSV evidence for reviewers and CI.

## Modules

| Module | Responsibility |
|---|---|
| `models.py` | Validated domain records, package loading, version comparison, and JSON input |
| `topology.py` | Unknown/self/cyclic dependency detection and update order |
| `ecu.py` | Dual-bank bootloader state, chunk reassembly, integrity, activation, commit, rollback |
| `network.py` | Deterministic delivery, one-time/permanent loss, corruption, and attempt trace |
| `orchestrator.py` | Preflight checks, retries, multi-ECU campaign coordination, transactional rollback |
| `runner.py` | Higher-level scenario isolation, expected-result comparison, and aggregate metrics |
| `reporting.py` | Reviewable and machine-readable evidence |
| `cli.py` | Reproducible manifest-validation and system-test commands |

## Update state

Each ECU begins with active slot A and an empty B slot. A successful download is reconstructed and hashed before its version is staged in the inactive slot. Activation preserves the previous slot until the complete campaign passes. A failed later ECU or health check rolls activated ECUs back in reverse order; a successful campaign commits all active slots.

## Extension seam

`EthernetLoopback.transmit(ecu_id, chunk_index, payload, attempt)` isolates transport behavior from campaign logic. A real authorized adapter would need addressing, sockets, protocol framing, timeouts, security, session lifecycle, logging, bandwidth limits, and integration tests. Those capabilities are outside this repository.
