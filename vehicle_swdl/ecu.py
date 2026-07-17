from __future__ import annotations

import hashlib

from .models import ECUDefinition, SoftwareImage


class DownloadFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ECUSimulator:
    """Deterministic dual-bank ECU bootloader model for system-level SWDL tests."""

    def __init__(self, definition: ECUDefinition) -> None:
        self.ecu_id = definition.ecu_id
        self.name = definition.name
        self.hardware_id = definition.hardware_id
        self.bootloader_version = definition.bootloader_version
        self.storage_capacity = definition.storage_capacity
        self.active_slot = definition.active_slot
        self.slot_versions = dict(definition.slot_versions)
        self._image: SoftwareImage | None = None
        self._chunks: dict[int, bytes] = {}
        self._expected_chunks = 0
        self._staged_slot: str | None = None
        self._previous_active: str | None = None

    @property
    def active_version(self) -> str:
        value = self.slot_versions[self.active_slot]
        assert value is not None
        return value

    @property
    def inactive_slot(self) -> str:
        return "B" if self.active_slot == "A" else "A"

    def begin(self, image: SoftwareImage, expected_chunks: int) -> None:
        if expected_chunks <= 0:
            raise DownloadFailure("INVALID_CHUNK_COUNT", "Expected chunk count must be positive")
        self._image = image
        self._chunks = {}
        self._expected_chunks = expected_chunks
        self._staged_slot = None

    def receive(self, index: int, payload: bytes) -> None:
        if self._image is None:
            raise DownloadFailure("NO_DOWNLOAD_SESSION", "No download session is active")
        if index < 0 or index >= self._expected_chunks:
            raise DownloadFailure("CHUNK_INDEX_OUT_OF_RANGE", f"Chunk index {index} is invalid")
        self._chunks[index] = bytes(payload)

    def finalize(self) -> str:
        if self._image is None:
            raise DownloadFailure("NO_DOWNLOAD_SESSION", "No download session is active")
        missing = [index for index in range(self._expected_chunks) if index not in self._chunks]
        if missing:
            raise DownloadFailure("MISSING_CHUNKS", f"Missing chunks: {missing}")
        payload = b"".join(self._chunks[index] for index in range(self._expected_chunks))
        if len(payload) != self._image.size:
            raise DownloadFailure("IMAGE_SIZE_MISMATCH", "Reassembled image size is incorrect")
        if hashlib.sha256(payload).hexdigest() != self._image.sha256:
            raise DownloadFailure("IMAGE_HASH_MISMATCH", "Reassembled image failed SHA-256 validation")
        target_slot = self.inactive_slot
        self.slot_versions[target_slot] = self._image.version
        self._staged_slot = target_slot
        return target_slot

    def activate(self) -> None:
        if self._staged_slot is None:
            raise DownloadFailure("NOT_STAGED", "No validated image is staged")
        self._previous_active = self.active_slot
        self.active_slot = self._staged_slot

    def rollback(self) -> bool:
        if self._previous_active is None:
            return False
        failed_slot = self.active_slot
        self.active_slot = self._previous_active
        self.slot_versions[failed_slot] = None
        self._previous_active = None
        self._staged_slot = None
        return True

    def commit(self) -> None:
        self._previous_active = None
        self._staged_slot = None
        self._image = None
        self._chunks = {}
        self._expected_chunks = 0
