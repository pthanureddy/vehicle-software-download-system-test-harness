from dataclasses import replace

import pytest

from vehicle_swdl.ecu import DownloadFailure, ECUSimulator


def chunks(payload, size=8):
    return [payload[offset : offset + size] for offset in range(0, len(payload), size)]


def test_ecu_exposes_active_and_inactive_slots(gateway_definition):
    ecu = ECUSimulator(gateway_definition)
    assert ecu.active_version == "5.4.2"
    assert ecu.inactive_slot == "B"


def test_begin_requires_positive_chunk_count(gateway_definition, gateway_image):
    with pytest.raises(DownloadFailure, match="positive"):
        ECUSimulator(gateway_definition).begin(gateway_image, 0)


def test_receive_requires_download_session(gateway_definition):
    with pytest.raises(DownloadFailure) as captured:
        ECUSimulator(gateway_definition).receive(0, b"data")
    assert captured.value.code == "NO_DOWNLOAD_SESSION"


def test_receive_rejects_out_of_range_index(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    ecu.begin(gateway_image, 1)
    with pytest.raises(DownloadFailure) as captured:
        ecu.receive(1, gateway_image.payload)
    assert captured.value.code == "CHUNK_INDEX_OUT_OF_RANGE"


def test_finalize_requires_all_chunks(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    payload_chunks = chunks(gateway_image.payload)
    ecu.begin(gateway_image, len(payload_chunks))
    ecu.receive(0, payload_chunks[0])
    with pytest.raises(DownloadFailure) as captured:
        ecu.finalize()
    assert captured.value.code == "MISSING_CHUNKS"


def test_finalize_rejects_hash_mismatch(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    payload_chunks = chunks(gateway_image.payload)
    ecu.begin(gateway_image, len(payload_chunks))
    for index, payload in enumerate(payload_chunks):
        if index == 0:
            payload = bytes([payload[0] ^ 0xFF]) + payload[1:]
        ecu.receive(index, payload)
    with pytest.raises(DownloadFailure) as captured:
        ecu.finalize()
    assert captured.value.code == "IMAGE_HASH_MISMATCH"


def test_finalize_stage_and_activate(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    payload_chunks = chunks(gateway_image.payload)
    ecu.begin(gateway_image, len(payload_chunks))
    for index, payload in enumerate(payload_chunks):
        ecu.receive(index, payload)
    assert ecu.finalize() == "B"
    ecu.activate()
    assert ecu.active_version == "5.5.0"
    assert ecu.active_slot == "B"


def test_activate_requires_staged_image(gateway_definition):
    with pytest.raises(DownloadFailure) as captured:
        ECUSimulator(gateway_definition).activate()
    assert captured.value.code == "NOT_STAGED"


def test_rollback_restores_previous_slot(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    payload_chunks = chunks(gateway_image.payload, 64)
    ecu.begin(gateway_image, 1)
    ecu.receive(0, payload_chunks[0])
    ecu.finalize()
    ecu.activate()
    assert ecu.rollback() is True
    assert ecu.active_slot == "A"
    assert ecu.active_version == "5.4.2"
    assert ecu.slot_versions["B"] is None


def test_rollback_without_activation_is_noop(gateway_definition):
    assert ECUSimulator(gateway_definition).rollback() is False


def test_commit_makes_activation_permanent(gateway_definition, gateway_image):
    ecu = ECUSimulator(gateway_definition)
    ecu.begin(gateway_image, 1)
    ecu.receive(0, gateway_image.payload)
    ecu.finalize()
    ecu.activate()
    ecu.commit()
    assert ecu.rollback() is False
    assert ecu.active_version == "5.5.0"
