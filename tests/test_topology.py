from dataclasses import replace

import pytest

from vehicle_swdl.models import FormatError
from vehicle_swdl.topology import dependency_order


def test_dependency_order_places_prerequisites_first(manifest):
    reversed_images = tuple(reversed(manifest.images))
    assert [image.ecu_id for image in dependency_order(reversed_images)] == [
        "gateway",
        "ccm",
        "infotainment",
    ]


def test_dependency_order_rejects_unknown_ecu(manifest):
    first = replace(manifest.images[0], depends_on=("missing",))
    with pytest.raises(FormatError, match="unknown"):
        dependency_order((first,) + manifest.images[1:])


def test_dependency_order_rejects_self_dependency(manifest):
    first = replace(manifest.images[0], depends_on=("gateway",))
    with pytest.raises(FormatError, match="itself"):
        dependency_order((first,) + manifest.images[1:])


def test_dependency_order_rejects_cycle(manifest):
    gateway = replace(manifest.images[0], depends_on=("ccm",))
    with pytest.raises(FormatError, match="Cyclic"):
        dependency_order((gateway,) + manifest.images[1:])
