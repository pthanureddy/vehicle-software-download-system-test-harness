# System Test Strategy

## Objective

Verify externally observable complete-system SWDL behavior across multiple ECU states, package constraints, transport failures, and post-install outcomes. The system runner treats a campaign as the test subject and checks final versions, status, failure code, updated/skipped counts, retry evidence, and rollback evidence.

## Test levels

- Unit tests cover version parsing, input validation, dependency graphs, ECU bootloader state, and network fault behavior.
- Integration tests connect manifest loading, topology, network, ECU, and orchestrator modules.
- Higher-level system scenarios execute complete campaigns from JSON inputs through final reports.
- CLI tests verify stable exit codes and repeatable report generation.

## Scenario design

The reference plan includes a nominal campaign, transient delivery loss, content corruption, low voltage, invalid ignition state, incompatible hardware, old bootloader, failed post-install health check, exhausted delivery retries, and already-current ECUs.

## Isolation and reproducibility

Every scenario starts from a deep copy of the same synthetic vehicle document. Network faults are deterministic and scoped by ECU/chunk index. Package payloads and expected SHA-256 values are committed with the test plan. No wall-clock, random, or external network dependency affects the results.

## Failure evidence

Reports preserve the campaign status, stable failure code, before/after software versions, update order, per-ECU outcomes, all network attempts, retries, and rollback totals. A mismatch between actual and expected results fails the CLI process so CI cannot silently accept a regression.
