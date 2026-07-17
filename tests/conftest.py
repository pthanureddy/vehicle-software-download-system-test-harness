from pathlib import Path

import pytest

from vehicle_swdl.models import load_manifest, load_vehicle


@pytest.fixture
def example_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def manifest(example_dir):
    return load_manifest(example_dir / "manifest.json")


@pytest.fixture
def vehicle(example_dir):
    return load_vehicle(example_dir / "vehicle.json")


@pytest.fixture
def gateway_image(manifest):
    return next(image for image in manifest.images if image.ecu_id == "gateway")


@pytest.fixture
def gateway_definition(vehicle):
    return next(ecu for ecu in vehicle.ecus if ecu.ecu_id == "gateway")
