# Software Download System Test Results

- Plan: swdl-complete-system-regression-2026.40.0
- Cases: 10
- Passed: 10
- Failed: 0
- Requirements: 10
- Network attempts: 77
- Network retries: 3
- Rollbacks: 4

## SWDL-SYS-001 / REQ-SWDL-001 - PASS

Install a compatible three-ECU baseline in dependency order

- Campaign status: COMPLETED
- Failure code: none
- Updated ECUs: 3
- Skipped ECUs: 0
- Network attempts/retries: 20/0
- Rollbacks: 0

## SWDL-SYS-002 / REQ-SWDL-002 - PASS

Retry and resume after a transient Ethernet-style chunk loss

- Campaign status: COMPLETED
- Failure code: none
- Updated ECUs: 3
- Skipped ECUs: 0
- Network attempts/retries: 21/1
- Rollbacks: 0

## SWDL-SYS-003 / REQ-SWDL-003 - PASS

Reject a corrupted image and roll back previously activated ECUs

- Campaign status: FAILED
- Failure code: IMAGE_HASH_MISMATCH
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 13/0
- Rollbacks: 1

## SWDL-SYS-004 / REQ-SWDL-004 - PASS

Block the campaign when battery voltage is below the download threshold

- Campaign status: BLOCKED
- Failure code: LOW_BATTERY_VOLTAGE
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 0/0
- Rollbacks: 0

## SWDL-SYS-005 / REQ-SWDL-005 - PASS

Block the campaign outside the permitted service ignition state

- Campaign status: BLOCKED
- Failure code: INVALID_IGNITION_STATE
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 0/0
- Rollbacks: 0

## SWDL-SYS-006 / REQ-SWDL-006 - PASS

Reject an image for incompatible ECU hardware

- Campaign status: BLOCKED
- Failure code: HARDWARE_INCOMPATIBLE
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 0/0
- Rollbacks: 0

## SWDL-SYS-007 / REQ-SWDL-007 - PASS

Reject an update when the bootloader is below the required version

- Campaign status: BLOCKED
- Failure code: BOOTLOADER_TOO_OLD
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 0/0
- Rollbacks: 0

## SWDL-SYS-008 / REQ-SWDL-008 - PASS

Roll back the complete campaign after a post-install health-check failure

- Campaign status: FAILED
- Failure code: POST_INSTALL_HEALTH_CHECK_FAILED
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 20/0
- Rollbacks: 3

## SWDL-SYS-009 / REQ-SWDL-009 - PASS

Fail safely when chunk delivery exhausts the network retry budget

- Campaign status: FAILED
- Failure code: NETWORK_RETRY_EXHAUSTED
- Updated ECUs: 0
- Skipped ECUs: 0
- Network attempts/retries: 3/2
- Rollbacks: 0

## SWDL-SYS-010 / REQ-SWDL-010 - PASS

Skip ECUs that already contain the target baseline

- Campaign status: COMPLETED
- Failure code: none
- Updated ECUs: 0
- Skipped ECUs: 3
- Network attempts/retries: 0/0
- Rollbacks: 0
