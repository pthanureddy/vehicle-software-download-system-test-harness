from __future__ import annotations

from .models import FaultPlan


class EthernetLoopback:
    """In-memory Ethernet-style chunk transport with deterministic fault injection."""

    def __init__(self, faults: FaultPlan) -> None:
        self.faults = faults
        self.trace: list[dict[str, object]] = []
        self._dropped_once: set[tuple[str, int]] = set()

    def transmit(self, ecu_id: str, index: int, payload: bytes, attempt: int) -> bytes | None:
        key = (ecu_id, index)
        if index in self.faults.drop_always.get(ecu_id, ()):
            self.trace.append(
                {"ecu_id": ecu_id, "chunk_index": index, "attempt": attempt, "outcome": "dropped"}
            )
            return None
        if index in self.faults.drop_once.get(ecu_id, ()) and key not in self._dropped_once:
            self._dropped_once.add(key)
            self.trace.append(
                {"ecu_id": ecu_id, "chunk_index": index, "attempt": attempt, "outcome": "dropped_once"}
            )
            return None
        delivered = bytes(payload)
        outcome = "delivered"
        if index in self.faults.corrupt.get(ecu_id, ()) and delivered:
            delivered = bytes([delivered[0] ^ 0xFF]) + delivered[1:]
            outcome = "corrupted"
        self.trace.append(
            {
                "ecu_id": ecu_id,
                "chunk_index": index,
                "attempt": attempt,
                "outcome": outcome,
                "byte_count": len(delivered),
            }
        )
        return delivered
