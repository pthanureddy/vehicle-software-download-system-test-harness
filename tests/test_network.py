from vehicle_swdl.models import FaultPlan
from vehicle_swdl.network import EthernetLoopback


def test_normal_transmission_preserves_payload():
    network = EthernetLoopback(FaultPlan.from_mapping(None))
    assert network.transmit("gateway", 0, b"abc", 1) == b"abc"
    assert network.trace[0]["outcome"] == "delivered"


def test_drop_once_recovers_on_next_attempt():
    network = EthernetLoopback(FaultPlan.from_mapping({"drop_once": {"gateway": [1]}}))
    assert network.transmit("gateway", 1, b"abc", 1) is None
    assert network.transmit("gateway", 1, b"abc", 2) == b"abc"
    assert [item["outcome"] for item in network.trace] == ["dropped_once", "delivered"]


def test_permanent_drop_never_delivers():
    network = EthernetLoopback(FaultPlan.from_mapping({"drop_always": {"gateway": [0]}}))
    assert network.transmit("gateway", 0, b"abc", 1) is None
    assert network.transmit("gateway", 0, b"abc", 2) is None


def test_corruption_changes_payload_and_is_traced():
    network = EthernetLoopback(FaultPlan.from_mapping({"corrupt": {"ccm": [0]}}))
    delivered = network.transmit("ccm", 0, b"abc", 1)
    assert delivered != b"abc"
    assert len(delivered) == 3
    assert network.trace[0]["outcome"] == "corrupted"


def test_faults_are_scoped_to_ecu_and_chunk():
    network = EthernetLoopback(FaultPlan.from_mapping({"drop_once": {"gateway": [1]}}))
    assert network.transmit("gateway", 0, b"a", 1) == b"a"
    assert network.transmit("ccm", 1, b"b", 1) == b"b"
